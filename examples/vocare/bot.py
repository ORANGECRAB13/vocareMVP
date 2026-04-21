"""Vocare voice bot with configurable STT/LLM/TTS via WebRTC transport.

The frontend sends service selections (stt, llm, tts) as part of the
/api/offer request body. The bot dynamically creates the chosen services
for each session.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

# GRC pilot imports — add GRC_pilot to path for its internal relative imports
sys.path.insert(0, str(Path(__file__).parent / "GRC_pilot"))
from database import init_db  # noqa: E402
from tools import book_bulky_waste, check_service_status, update_booking_date, get_bin_collection_zone  # noqa: E402
from knowledge import BULKY_WASTE_KNOWLEDGE  # noqa: E402
from da_knowledge import DA_KNOWLEDGE  # noqa: E402

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

# ---------------------------------------------------------------------------
# CRITICAL FIX: aioice does NOT handle TURN DATA indications (RFC 5766 §7.2).
# When the phone sends STUN binding checks through its TURN relay, Twilio
# forwards them to the bot's TURN allocation as DATA indications. aioice only
# handles ChannelData (bound channels) and STUN responses — DATA indications
# are logged then DROPPED, so the bot never responds to the phone's checks
# and ICE times out after 60s.
#
# Fix: monkey-patch TurnClientMixin.datagram_received to extract the payload
# from DATA indications and forward it to the ICE layer.
# Also register the missing DATA attribute (0x0013) in aioice's STUN parser.
# ---------------------------------------------------------------------------
import struct
from typing import cast, Union

from aioice import stun as _stun_mod
from aioice import turn as _turn_mod
from aioice.ice import TransportPolicy
import aiortc.rtcicetransport as _ice_mod

# 1) Register DATA attribute (0x0013) — aioice's STUN parser doesn't know it
if 0x0013 not in _stun_mod.ATTRIBUTES_BY_TYPE:
    _data_attr = (0x0013, "DATA", _stun_mod.pack_bytes, _stun_mod.unpack_bytes)
    _stun_mod.ATTRIBUTES_BY_TYPE[0x0013] = _data_attr
    _stun_mod.ATTRIBUTES_BY_NAME["DATA"] = _data_attr
    logger.info("Registered missing STUN DATA attribute (0x0013) in aioice")


# 2) Monkey-patch TurnClientMixin.datagram_received to handle DATA indications
def _patched_datagram_received(self, data: Union[bytes, str], addr: tuple) -> None:
    data = cast(bytes, data)

    # Demultiplex ChannelData (existing logic — bound channels)
    if len(data) >= 4 and _turn_mod.is_channel_data(data):
        channel, length = struct.unpack("!HH", data[0:4])
        if len(data) >= length + 4 and self.receiver is not None:
            peer_address = self.channel_to_peer.get(channel)
            if peer_address:
                payload = data[4 : 4 + length]
                self.receiver.datagram_received(payload, peer_address)
        return

    try:
        message = _stun_mod.parse_message(data)
    except ValueError:
        return

    # ── NEW: Handle DATA indication (RFC 5766 §7.2) ──────────────────────
    # Extracts XOR-PEER-ADDRESS + DATA payload and forwards to ICE layer,
    # exactly like ChannelData does for bound channels.
    if (
        message.message_method == _stun_mod.Method.DATA
        and message.message_class == _stun_mod.Class.INDICATION
    ):
        peer_address = message.attributes.get("XOR-PEER-ADDRESS")
        payload = message.attributes.get("DATA")
        if peer_address and payload is not None and self.receiver is not None:
            self.receiver.datagram_received(payload, peer_address)
        return

    # Handle STUN responses/errors for pending transactions (existing logic)
    if (
        message.message_class == _stun_mod.Class.RESPONSE
        or message.message_class == _stun_mod.Class.ERROR
    ) and message.transaction_id in self.transactions:
        transaction = self.transactions[message.transaction_id]
        transaction.response_received(message, addr)


_turn_mod.TurnClientMixin.datagram_received = _patched_datagram_received
logger.info("Monkey-patched aioice: TurnClientMixin now handles DATA indications")


# 3) Force relay-only ICE transport policy on the bot side
_orig_connection_kwargs = _ice_mod.connection_kwargs


def _relay_only_connection_kwargs(servers):
    kwargs = _orig_connection_kwargs(servers)
    kwargs["transport_policy"] = TransportPolicy.RELAY
    return kwargs


_ice_mod.connection_kwargs = _relay_only_connection_kwargs
logger.info("Monkey-patched aiortc: bot ICE transport policy forced to RELAY-only")

# ---------------------------------------------------------------------------
# Route aioice / aiortc stdlib logs through loguru
# ---------------------------------------------------------------------------


class _InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


for _name in ("aioice", "aiortc"):
    _logger = logging.getLogger(_name)
    _logger.handlers = [_InterceptHandler()]
    _logger.setLevel(logging.WARNING)
    _logger.propagate = False

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    FunctionCallInProgressFrame,
    InterimTranscriptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMRunFrame,
    LLMTextFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSUpdateSettingsFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.transcriptions.language import Language
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.turns.user_mute.mute_until_first_bot_complete_user_mute_strategy import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.llm_service import LLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

load_dotenv(override=True)

# Suppress pipecat internal DEBUG/TRACE noise — keep only INFO and above.
# Re-enable temporarily by setting VOCARE_LOG_LEVEL=DEBUG in the environment.
_log_level = os.getenv("VOCARE_LOG_LEVEL", "INFO").upper()
logger.remove()
logger.add(sys.stderr, level=_log_level, colorize=True,
           format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level:<7}</level> | {message}")

# ---------------------------------------------------------------------------
# LTS-VoiceAgent: Background Thinker
# ---------------------------------------------------------------------------

THINKER_SYSTEM_PROMPT = (
    "You are an intent/entity extraction engine for a council voice bot. "
    "Given the user's speech transcript, output ONLY valid JSON with this schema:\n"
    '{"intent": "bin_collection | bulky_waste | da_inquiry | general", '
    '"entities": {"address": "...", "name": "...", "phone": "...", "date": "..."}, '
    '"confidence": 0.0-1.0}\n'
    "Rules:\n"
    "- intent: classify the user's primary need\n"
    "- entities: extract any mentioned values, use null for missing ones\n"
    "- confidence: your certainty in the intent classification\n"
    "- For partial/incomplete speech, do your best with what's available\n"
    "- Output ONLY the JSON object, no explanation"
)

FILLERS = [
    "Let me look that up for you.",
    "Just a moment while I check that.",
    "One moment please.",
]


class ThinkerProcessor(FrameProcessor):
    """Runs a background 8B LLM to pre-extract intent/entities from STT transcripts.

    Sits between STT and user_aggregator. Intercepts InterimTranscriptionFrame
    (with 200ms debounce) and TranscriptionFrame (immediately) to fire an
    out-of-pipeline Groq inference. The result is stored in thinker_state and
    later injected by ContextEnricherProcessor. All frames pass through unchanged.
    """

    def __init__(self, thinker_llm: GroqLLMService, **kwargs):
        super().__init__(**kwargs)
        self._thinker_llm = thinker_llm
        self._latest_state: dict | None = None
        self._state_lock = asyncio.Lock()
        self._debounce_task: asyncio.Task | None = None

    @property
    def thinker_state(self) -> dict | None:
        return self._latest_state

    async def clear_state(self):
        async with self._state_lock:
            self._latest_state = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            await self._maybe_fire_interim_inference(frame.text)
        elif isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            await self._fire_final_inference(frame.text)

        await self.push_frame(frame, direction)

    async def _maybe_fire_interim_inference(self, text: str):
        """Debounced interim inference — fires 200ms after the last interim frame."""
        if self._debounce_task and not self._debounce_task.done():
            await self.cancel_task(self._debounce_task)

        async def _debounced():
            await asyncio.sleep(0.2)
            await self._run_thinker(text)

        self._debounce_task = self.create_task(_debounced(), "thinker_debounce")

    async def _fire_final_inference(self, text: str):
        """Cancel any pending interim task and fire inference on the final transcript."""
        if self._debounce_task and not self._debounce_task.done():
            await self.cancel_task(self._debounce_task)
            self._debounce_task = None
        self.create_task(self._run_thinker(text), "thinker_final")

    async def _run_thinker(self, transcript: str):
        try:
            temp_context = LLMContext()
            temp_context.add_message({"role": "user", "content": transcript})
            result = await self._thinker_llm.run_inference(
                temp_context,
                max_tokens=200,
                system_instruction=THINKER_SYSTEM_PROMPT,
            )
            if result:
                state = json.loads(result)
                async with self._state_lock:
                    self._latest_state = state
                logger.info(f"Thinker extracted: {state}")
        except asyncio.CancelledError:
            raise
        except json.JSONDecodeError as e:
            logger.warning(f"Thinker JSON parse error: {e}")
        except Exception as e:
            logger.warning(f"Thinker inference error: {e}")


class ContextEnricherProcessor(FrameProcessor):
    """Injects Thinker pre-extraction state into the Speaker LLM context.

    Sits between user_aggregator and Speaker LLM. On LLMContextFrame, reads
    thinker_state and adds a [THINKER_STATE] system message so the Speaker
    can skip extraction and act immediately.
    """

    def __init__(self, thinker_processor: ThinkerProcessor, **kwargs):
        super().__init__(**kwargs)
        self._thinker = thinker_processor

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            state = self._thinker.thinker_state
            if state and state.get("confidence", 0.0) >= 0.5:
                injection = (
                    f"[THINKER_STATE] Pre-extracted from user speech:\n{json.dumps(state)}\n"
                    "Use this to respond faster. If intent and required entities are present, "
                    "proceed directly to the appropriate tool call."
                )
                frame.context.add_message({"role": "system", "content": injection})
                logger.info(f"Injected thinker state: intent={state.get('intent')} "
                            f"confidence={state.get('confidence')}")
                await self._thinker.clear_state()

        await self.push_frame(frame, direction)


class FillerTTSProcessor(FrameProcessor):
    """Injects a filler TTS phrase when a tool call starts, masking tool latency.

    Sits between Speaker LLM and TTS. On FunctionCallInProgressFrame, pushes a
    TTSSpeakFrame with a cycling filler phrase before passing the original frame.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._filler_index = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, FunctionCallInProgressFrame) and direction == FrameDirection.DOWNSTREAM:
            filler = FILLERS[self._filler_index % len(FILLERS)]
            self._filler_index += 1
            await self.push_frame(TTSSpeakFrame(text=filler), direction)

        await self.push_frame(frame, direction)


class LanguageSwitchProcessor(FrameProcessor):
    """Detects the user's spoken language and updates the TTS voice/language accordingly.

    Sits between ThinkerProcessor and user_aggregator. Watches TranscriptionFrame
    for language changes. On a change, pushes a TTSUpdateSettingsFrame downstream
    to reconnect the ElevenLabs WebSocket with the correct voice and language code.
    """

    def __init__(self, tts, en_voice_id: str, multilingual_voice_id: str, **kwargs):
        super().__init__(**kwargs)
        self._tts = tts
        self._en_voice_id = en_voice_id
        self._multilingual_voice_id = multilingual_voice_id
        self._current_language: Language | None = Language.EN

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            # None means STT didn't tag a language — treat as English (the default/unmarked case).
            # Normalise all Chinese variants (ZH, ZH_CN, ZH_TW, ZH_HK …) to a single sentinel.
            raw = frame.language
            is_chinese = raw is not None and raw.value.startswith("zh")
            target = Language.ZH if is_chinese else Language.EN

            if target != self._current_language:
                self._current_language = target
                await self._switch_language(target)

        await self.push_frame(frame, direction)

    async def _switch_language(self, language: Language):
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

        is_chinese = language == Language.ZH
        voice = self._multilingual_voice_id if is_chinese else self._en_voice_id
        lang_setting = Language.ZH if is_chinese else Language.EN

        delta = ElevenLabsTTSService.Settings(voice=voice, language=lang_setting)
        await self.push_frame(
            TTSUpdateSettingsFrame(delta=delta, service=self._tts),
            FrameDirection.DOWNSTREAM,
        )
        logger.info(f"Language switch → {'zh' if is_chinese else 'en'} | voice={'multilingual' if is_chinese else 'english'}")


SYSTEM_INSTRUCTION_GRC = (
    "You are a voice agent for Georges River Council. Your name is Maya. "
    "You help residents with three services: bin collection day lookups, "
    "bulky waste collection bookings, and development application inquiries. "
    "Speak naturally, warmly, and concisely — one or two sentences at a time. "
    "Never use lists, bullet points, or emojis. "
    "Do not use filler phrases like 'Certainly!' or 'Of course!'. "

    # --- Service: Bin collection ---
    "For bin collection day: always call get_bin_collection_day with the resident's "
    "full street address. Never guess or invent a collection day. "

    # --- Service: Bulky waste ---
    "For bulky waste booking: call book_bulky_waste once you have the resident's "
    "full name, phone number, address, and a preferred collection date in YYYY-MM-DD. "
    "Collect details conversationally — do not ask for all at once. "
    "To check remaining entitlements, call check_service_status with their phone number. "
    "To change a booking date, call update_booking_date. "

    # --- Service: Development applications ---
    "For DA inquiries: answer from the knowledge base below. "
    "Direct residents to lodge via the NSW Planning Portal only. "
    "For specific advice, refer them to the Duty Planner on 9330 6400. "

    # --- Tone ---
    "Always answer only what was asked. Be brief and direct. "
    "Never invent information not in the knowledge base or tool results. "

    # --- Multilingual ---
    "LANGUAGE RULE (mandatory): match the language of your response to the language "
    "of the user's most recent message — every single turn, no exceptions. "
    "If their last message was in English, respond in English. "
    "If their last message was in Mandarin Chinese, respond in Mandarin Chinese. "
    "A single English word or sentence from the user means the entire response must be in English. "
    "Never continue in a previous language if the user has switched. "

    # --- Thinker acceleration ---
    "You may receive a [THINKER_STATE] system message with pre-extracted intent and entities. "
    "When present, use it to respond faster: "
    "if intent is bin_collection and address is present, call get_bin_collection_day immediately. "
    "If intent is bulky_waste and all four fields (name, phone, address, date) are present, "
    "call book_bulky_waste immediately. "
    "If entities are partially present, confirm only the missing ones. "
    "If no THINKER_STATE is present, proceed as normal. "

    "\n\n"
    + BULKY_WASTE_KNOWLEDGE
    + "\n\n"
    + DA_KNOWLEDGE
)

# ---------------------------------------------------------------------------
# Service factory functions
# ---------------------------------------------------------------------------


def create_stt(name: str):
    """Create an STT service by name."""
    if name == "deepgram":
        from pipecat.services.deepgram.stt import DeepgramSTTService

        return DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    elif name == "elevenlabs":
        from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService

        return ElevenLabsRealtimeSTTService(api_key=os.getenv("ELEVENLABS_API_KEY"))
    else:
        raise ValueError(f"Unknown STT service: {name}")


def create_llm(name: str, system_instruction: str = ""):
    """Create an LLM service by name."""
    if name == "mistral":
        from pipecat.services.mistral.llm import MistralLLMService

        return MistralLLMService(
            api_key=os.getenv("MISTRAL_API_KEY"),
            settings=MistralLLMService.Settings(
                system_instruction=system_instruction,
            ),
        )
    elif name == "groq":
        from pipecat.services.groq.llm import GroqLLMService

        return GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            settings=GroqLLMService.Settings(
                system_instruction=system_instruction,
            ),
        )
    else:
        raise ValueError(f"Unknown LLM service: {name}")


def create_tts(name: str):
    """Create a TTS service by name."""
    if name == "elevenlabs":
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

        return ElevenLabsTTSService(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            settings=ElevenLabsTTSService.Settings(
                voice=os.getenv("ELEVENLABS_VOICE_ID"),
            ),
        )
    else:
        raise ValueError(f"Unknown TTS service: {name}")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

pcs_map: Dict[str, SmallWebRTCConnection] = {}
graph_event_queues: Dict[str, asyncio.Queue] = {}

# Demo mode shared state
demo_events: list[dict] = []      # append-only list of graph events (fan-out to multiple viewers)
demo_pc_id: str | None = None     # presenter's pc_id (None = no active demo)

def fetch_twilio_ice_servers():
    """Fetch fresh TURN credentials from Twilio Network Traversal Service.

    Returns a list of IceServer objects (for aiortc) plus the raw dicts
    (for the frontend). Falls back to STUN-only if Twilio not configured.
    """
    import base64
    import urllib.request

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        logger.warning("Twilio credentials missing — falling back to STUN only")
        stun = [{"urls": "stun:stun.l.google.com:19302"}]
        return [IceServer(urls="stun:stun.l.google.com:19302")], stun

    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Tokens.json"
        auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
        req = urllib.request.Request(
            url,
            data=b"",  # POST with empty body
            headers={"Authorization": f"Basic {auth}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        raw_servers = data.get("ice_servers", [])
        ice_list = []
        for s in raw_servers:
            urls = s.get("url") or s.get("urls")
            if not urls:
                continue
            ice_list.append(
                IceServer(
                    urls=urls,
                    username=s.get("username"),
                    credential=s.get("credential"),
                )
            )
        # Normalize for frontend: use "urls" key
        frontend_servers = [
            {
                "urls": s.get("url") or s.get("urls"),
                **({"username": s["username"]} if s.get("username") else {}),
                **({"credential": s["credential"]} if s.get("credential") else {}),
            }
            for s in raw_servers
        ]
        logger.info(f"Fetched {len(ice_list)} ICE servers from Twilio")
        return ice_list, frontend_servers
    except Exception as e:
        logger.error(f"Failed to fetch Twilio ICE servers: {e}")
        stun = [{"urls": "stun:stun.l.google.com:19302"}]
        return [IceServer(urls="stun:stun.l.google.com:19302")], stun


# Fetched fresh on each /api/offer so credentials are always valid.
ice_servers = [IceServer(urls="stun:stun.l.google.com:19302")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-load Silero VAD ONNX session once (avoids 50–250ms load per session).
    # The InferenceSession is stateless and safe to share; each SileroVADAnalyzer
    # still gets its own mutable state (_model._state, _context, etc.).
    from pipecat.audio.vad.silero import SileroOnnxModel

    _warmup_vad = SileroVADAnalyzer()
    _cached_session = _warmup_vad._model.session

    def _fast_init(self, path, force_onnx_cpu=True):
        self.session = _cached_session
        self.reset_states()
        self.sample_rates = [8000, 16000]

    SileroOnnxModel.__init__ = _fast_init
    logger.info("Silero VAD ONNX session pre-loaded")

    init_db()
    logger.info("SQLite residents DB initialised")

    yield

    coros = [pc.disconnect() for pc in pcs_map.values()]
    await asyncio.gather(*coros)
    pcs_map.clear()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


async def _put_graph_event(event_queue: asyncio.Queue, event: dict):
    """Put an event into the session queue.

    If demo mode is active, also appends to demo_events for fan-out to viewers.
    """
    await event_queue.put(event)
    if demo_pc_id is not None:
        demo_events.append(event)


# ---------------------------------------------------------------------------
# Graph highlight observer
# ---------------------------------------------------------------------------


class TranscriptionObserver(BaseObserver):
    """Watches STT and LLM frames to emit transcript events to the frontend.

    Pushes 'user_transcription' events on final TranscriptionFrames and
    'bot_transcription' events when the LLM finishes a full response.
    """

    def __init__(self, event_queue: asyncio.Queue):
        super().__init__()
        self._event_queue = event_queue
        self._bot_buffer = ""

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if data.direction != FrameDirection.DOWNSTREAM:
            return

        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if text:
                await _put_graph_event(
                    self._event_queue, {"type": "user_transcription", "text": text}
                )

        elif isinstance(frame, LLMTextFrame) and isinstance(data.source, LLMService):
            self._bot_buffer += frame.text

        elif isinstance(frame, LLMFullResponseEndFrame):
            text = self._bot_buffer.strip()
            self._bot_buffer = ""
            if text:
                await _put_graph_event(
                    self._event_queue, {"type": "bot_transcription", "text": text}
                )


# ---------------------------------------------------------------------------
# Latency observer
# ---------------------------------------------------------------------------


class LatencyObserver(BaseObserver):
    """Measures end-to-end turn latency through the pipeline.

    Tracks four timestamps per turn:

        t_vad_stop     — UserStoppedSpeakingFrame detected
        t_transcription — first final TranscriptionFrame
        t_llm_first    — first LLMTextFrame from the LLM
        t_tts_start    — TTSStartedFrame (TTS begins producing audio)

    Derived intervals::

        STT latency   = t_transcription - t_vad_stop
        LLM latency   = t_llm_first    - t_transcription
        TTS latency   = t_tts_start    - t_llm_first
        TOTAL TTFB    = t_tts_start    - t_vad_stop

    Tool calls (e.g. geocoding) sit inside the LLM interval and are flagged
    in the log row.
    """

    def __init__(self):
        super().__init__()
        self._reset()
        self._turn_count = 0
        self._history: list[dict] = []
        # Buffer: holds the timestamp of the most recent TranscriptionFrame so
        # that if it arrives fractionally before UserStoppedSpeakingFrame (which
        # is common) we can still record t_transcription correctly.
        self._pending_transcription: float | None = None

    def _reset(self):
        self._t_vad_stop      = None
        self._t_transcription = None
        self._t_llm_first     = None
        self._t_tool_start    = None
        self._t_tool_end      = None
        self._t_tts_start     = None
        self._has_tool_call   = False
        self._logged          = False

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if data.direction != FrameDirection.DOWNSTREAM:
            return

        now = data.timestamp / 1_000_000_000  # nanoseconds → seconds

        if isinstance(frame, TranscriptionFrame):
            # Buffer unconditionally — may arrive just before UserStoppedSpeakingFrame
            self._pending_transcription = now
            if self._t_vad_stop is not None and self._t_transcription is None:
                self._t_transcription = now

        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._reset()
            self._t_vad_stop = now
            # Apply buffered transcription if it arrived in the same ~50ms window
            if (
                self._pending_transcription is not None
                and now - self._pending_transcription < 0.05
            ):
                self._t_transcription = self._pending_transcription

        elif isinstance(frame, FunctionCallInProgressFrame):
            self._has_tool_call = True
            if self._t_tool_start is None:
                self._t_tool_start = now

        elif isinstance(frame, LLMTextFrame):
            # Fires on both LLM #1 (no-tool) and LLM #2 (after tool result).
            # Record the first LLMTextFrame regardless — for tool turns this
            # will be the LLM #2 first token, which is the right boundary for
            # "LLM done → TTS starts".
            if self._t_vad_stop is not None and self._t_llm_first is None:
                if not self._has_tool_call or self._t_tool_start is not None:
                    self._t_llm_first = now
                    # If tool ran, close the tool window
                    if self._has_tool_call and self._t_tool_end is None:
                        self._t_tool_end = now

        elif isinstance(frame, TTSStartedFrame):
            if self._t_vad_stop is not None and not self._logged:
                self._t_tts_start = now
                self._logged = True
                self._log_turn()

    def _log_turn(self):
        t0 = self._t_vad_stop
        t1 = self._t_transcription
        t2 = self._t_llm_first
        t3 = self._t_tts_start
        ts = self._t_tool_start
        te = self._t_tool_end

        def ms(a, b):
            return f"{(b - a) * 1000:6.0f} ms" if a is not None and b is not None else "    -- "

        stt_ms   = (t1 - t0) * 1000 if t0 and t1 else None
        llm1_ms  = (ts - t1) * 1000 if t1 and ts else None   # STT → tool dispatch
        tool_ms  = (te - ts) * 1000 if ts and te else None   # tool execution
        llm2_ms  = (t2 - te) * 1000 if te and t2 else None   # tool result → LLM reply token
        llm_ms   = (t2 - t1) * 1000 if t1 and t2 else None   # combined if no tool split
        tts_ms   = (t3 - t2) * 1000 if t2 and t3 else None
        total_ms = (t3 - t0) * 1000 if t0 and t3 else None

        self._turn_count += 1
        self._history.append({
            "turn": self._turn_count, "stt_ms": stt_ms,
            "llm_ms": llm_ms, "tts_ms": tts_ms,
            "total_ms": total_ms, "tool": self._has_tool_call,
        })

        tool_flag = " [tool]" if self._has_tool_call else ""
        sep = "-" * 62

        logger.info(sep)
        logger.info(f"  LATENCY BREAKDOWN — Turn {self._turn_count}{tool_flag}")
        logger.info(sep)
        logger.info(f"  VAD stop  → STT final        {ms(t0, t1)}")
        if self._has_tool_call and ts:
            logger.info(f"  STT final → LLM #1 decision  {ms(t1, ts)}")
            logger.info(f"  Tool execution               {ms(ts, te)}")
            logger.info(f"  Tool result → LLM #2 token   {ms(te, t2)}")
        else:
            logger.info(f"  STT final → LLM 1st token    {ms(t1, t2)}")
        logger.info(f"  LLM token → TTS start        {ms(t2, t3)}")
        logger.info(f"  {'-' * 60}")
        logger.info(f"  VAD stop  → TTS start        {ms(t0, t3)}   <- TOTAL TTFB")
        logger.info(sep)

        totals = [r["total_ms"] for r in self._history if r["total_ms"] is not None]
        if len(totals) > 1:
            avg = sum(totals) / len(totals)
            logger.info(
                f"  Avg TTFB over {len(totals)} turns: {avg:.0f} ms"
                + (f"  (this turn: {total_ms:.0f} ms)" if total_ms else "")
            )
            logger.info(sep)


# ---------------------------------------------------------------------------
# Bot pipeline
# ---------------------------------------------------------------------------


async def run_bot(
    webrtc_connection: SmallWebRTCConnection,
    stt_name: str,
    llm_name: str,
    tts_name: str,
):
    logger.info(f"Starting bot — STT={stt_name}, LLM={llm_name}, TTS={tts_name}")

    system_instruction = SYSTEM_INSTRUCTION_GRC

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    stt = create_stt(stt_name)
    llm = create_llm(llm_name, system_instruction=system_instruction)
    tts = create_tts(tts_name)

    thinker_llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqLLMService.Settings(
            model="llama-3.1-8b-instant",
            extra={"response_format": {"type": "json_object"}},
        ),
    )
    thinker_processor = ThinkerProcessor(thinker_llm=thinker_llm)
    context_enricher = ContextEnricherProcessor(thinker_processor=thinker_processor)
    filler_tts = FillerTTSProcessor()
    lang_switch = LanguageSwitchProcessor(
        tts=tts,
        en_voice_id=os.getenv("ELEVENLABS_VOICE_ID", ""),
        multilingual_voice_id=os.getenv("ELEVENLABS_MULTILINGUAL_VOICE_ID", os.getenv("ELEVENLABS_VOICE_ID", "")),
    )

    # Attach transcript observer so the frontend can display live conversation
    pc_id = webrtc_connection.pc_id
    event_queue = graph_event_queues.get(pc_id)
    latency_observer = LatencyObserver()
    observers = [latency_observer]
    if event_queue:
        transcript_observer = TranscriptionObserver(event_queue)
        observers.append(transcript_observer)

    async def handle_book_bulky_waste(params: FunctionCallParams):
        name = params.arguments.get("name", "").strip()
        phone = params.arguments.get("phone", "").strip()
        address = params.arguments.get("address", "").strip()
        preferred_date = params.arguments.get("preferred_date", "").strip()
        logger.info(f"Function call: book_bulky_waste({name}, {phone})")
        try:
            result = book_bulky_waste(
                {"name": name, "phone": phone, "address": address, "preferred_date": preferred_date}
            )
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"book_bulky_waste failed: {e}")
            await params.result_callback({"error": "Failed to book collection. Please try again."})

    async def handle_check_service_status(params: FunctionCallParams):
        phone = params.arguments.get("phone", "").strip()
        logger.info(f"Function call: check_service_status({phone})")
        try:
            result = check_service_status({"phone": phone})
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"check_service_status failed: {e}")
            await params.result_callback({"error": "Failed to check status. Please try again."})

    async def handle_update_booking_date(params: FunctionCallParams):
        phone = params.arguments.get("phone", "").strip()
        name = params.arguments.get("name", "").strip()
        new_date = params.arguments.get("new_date", "").strip()
        logger.info(f"Function call: update_booking_date({phone})")
        try:
            result = update_booking_date({"phone": phone, "name": name, "new_date": new_date})
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"update_booking_date failed: {e}")
            await params.result_callback({"error": "Failed to update booking. Please try again."})

    async def handle_get_bin_collection_day(params: FunctionCallParams):
        address = params.arguments.get("address", "").strip()
        logger.info(f"Function call: get_bin_collection_day({address})")
        try:
            result = await asyncio.to_thread(get_bin_collection_zone, {"address": address})
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"get_bin_collection_day failed: {e}")
            await params.result_callback(
                {"error": "I couldn't look up the bin collection day. Please try again."}
            )

    # Register GRC tools on the LLM and build schema
    llm.register_function("book_bulky_waste", handle_book_bulky_waste)
    llm.register_function("check_service_status", handle_check_service_status)
    llm.register_function("update_booking_date", handle_update_booking_date)
    llm.register_function("get_bin_collection_day", handle_get_bin_collection_day)

    book_bulky_waste_schema = FunctionSchema(
        name="book_bulky_waste",
        description=(
            "Book a Bulky Waste Collection for a resident. "
            "Call once you have their full name, phone number, address, "
            "and preferred collection date."
        ),
        properties={
            "name": {"type": "string", "description": "Resident's full name"},
            "phone": {"type": "string", "description": "Resident's phone number"},
            "address": {"type": "string", "description": "Full property address"},
            "preferred_date": {
                "type": "string",
                "description": "Preferred collection date in YYYY-MM-DD format",
            },
        },
        required=["name", "phone", "address", "preferred_date"],
    )
    check_service_status_schema = FunctionSchema(
        name="check_service_status",
        description=(
            "Check how many bulky waste collections a resident has remaining this year. "
            "Call when a resident asks about their entitlements or remaining bookings."
        ),
        properties={
            "phone": {"type": "string", "description": "Resident's phone number"},
        },
        required=["phone"],
    )
    update_booking_date_schema = FunctionSchema(
        name="update_booking_date",
        description=(
            "Change the date of an existing bulky waste booking. "
            "Call when a resident wants to reschedule their collection."
        ),
        properties={
            "phone": {"type": "string", "description": "Resident's phone number"},
            "name": {"type": "string", "description": "Resident's full name"},
            "new_date": {
                "type": "string",
                "description": "New preferred date in YYYY-MM-DD format",
            },
        },
        required=["phone", "name", "new_date"],
    )
    get_bin_collection_day_schema = FunctionSchema(
        name="get_bin_collection_day",
        description=(
            "Look up the bin collection day for a resident's address. "
            "Call when a resident asks what day their bins are collected."
        ),
        properties={
            "address": {
                "type": "string",
                "description": "Full street address within the Georges River LGA",
            },
        },
        required=["address"],
    )
    tools = ToolsSchema(
        standard_tools=[
            book_bulky_waste_schema,
            check_service_status_schema,
            update_booking_date_schema,
            get_bin_collection_day_schema,
        ]
    )

    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            thinker_processor,
            lang_switch,
            user_aggregator,
            context_enricher,
            llm,
            filler_tts,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=observers,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        context.add_message({
            "role": "system",
            "content": (
                "Greet the caller with: "
                "'Hi, I'm Maya from Georges River Council — how can I help you today?'"
            ),
        })
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        global demo_pc_id
        logger.info("Client disconnected")
        pc_id = webrtc_connection.pc_id
        queue = graph_event_queues.pop(pc_id, None)
        if queue:
            await queue.put(None)  # Signal SSE to close
        if demo_pc_id == pc_id:
            demo_pc_id = None
            logger.info("Demo presenter disconnected — demo session ended")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path) as f:
        return HTMLResponse(content=f.read())


@app.get("/api/ice")
async def get_ice_servers():
    """Return fresh TURN/STUN credentials for the frontend RTCPeerConnection."""
    _, frontend_servers = fetch_twilio_ice_servers()
    return {"iceServers": frontend_servers}


@app.post("/api/offer")
async def offer(request: dict, background_tasks: BackgroundTasks):
    global demo_pc_id, demo_events
    pc_id = request.get("pc_id")

    # Log incoming candidates from the peer (diagnose WebRTC ICE issues)
    offer_sdp = request.get("sdp", "")
    candidates = [line.strip() for line in offer_sdp.split("\n") if "candidate" in line]
    logger.info(f"Peer offered {len(candidates)} candidate line(s):")
    for c in candidates:
        logger.info(f"  {c}")

    # Extract service selections (defaults if not provided)
    stt_name = request.get("stt", "elevenlabs")
    llm_name = request.get("llm", "groq")
    tts_name = request.get("tts", "elevenlabs")
    mode = request.get("mode", "indiv")

    if pc_id and pc_id in pcs_map:
        pipecat_connection = pcs_map[pc_id]
        logger.info(f"Reusing existing connection for pc_id: {pc_id}")
        await pipecat_connection.renegotiate(
            sdp=request["sdp"],
            type=request["type"],
            restart_pc=request.get("restart_pc", False),
        )
    else:
        # Fetch fresh Twilio ICE servers for this session
        session_ice_servers, _ = fetch_twilio_ice_servers()
        pipecat_connection = SmallWebRTCConnection(session_ice_servers)
        await pipecat_connection.initialize(sdp=request["sdp"], type=request["type"])

        @pipecat_connection.event_handler("closed")
        async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
            logger.info(f"Discarding peer connection for pc_id: {webrtc_connection.pc_id}")
            pcs_map.pop(webrtc_connection.pc_id, None)

        background_tasks.add_task(
            run_bot, pipecat_connection, stt_name, llm_name, tts_name
        )

    answer = pipecat_connection.get_answer()

    # Filter the answer SDP to keep ONLY `typ relay` ICE candidates.
    # The phone uses iceTransportPolicy: 'relay' so it only advertises relay
    # candidates. By stripping our host/srflx candidates here we guarantee
    # every candidate pair that forms is a relay↔relay pair routed via
    # Twilio's TURN servers — no private IPs, no srflx that would fail
    # CreatePermission on the phone's TURN allocation.
    filtered_sdp_lines = []
    kept_candidates = 0
    dropped_candidates = 0
    for line in answer["sdp"].split("\r\n"):
        stripped = line.strip()
        if stripped.startswith("a=candidate:") or stripped.startswith("candidate:"):
            if "typ relay" in stripped:
                filtered_sdp_lines.append(line)
                kept_candidates += 1
            else:
                dropped_candidates += 1
            continue
        filtered_sdp_lines.append(line)
    answer["sdp"] = "\r\n".join(filtered_sdp_lines)
    logger.info(
        f"Answer SDP filtered: kept {kept_candidates} relay candidate(s), "
        f"dropped {dropped_candidates} non-relay candidate(s)"
    )
    if kept_candidates == 0:
        logger.error(
            "No relay candidates in answer SDP! Bot failed to allocate a TURN "
            "relay via Twilio — mobile clients will not connect."
        )

    pc_id_value = answer["pc_id"]
    pcs_map[pc_id_value] = pipecat_connection

    # Create SSE event queue for transcript and graph events
    graph_event_queues[pc_id_value] = asyncio.Queue()

    # Demo mode: register this connection as the presenter
    if mode == "demo":
        demo_pc_id = pc_id_value
        demo_events = []
        logger.info(f"Demo mode activated — presenter pc_id: {pc_id_value}")

    return answer


@app.get("/api/graph/poll")
async def graph_poll(pc_id: str):
    """Polling endpoint — drains queued graph events and returns them as JSON.

    Replaces SSE because Cloudflare free tunnels unreliably buffer/drop
    streaming responses. Frontend polls this every ~250ms.
    """
    queue = graph_event_queues.get(pc_id)
    if not queue:
        return {"events": [], "closed": False}

    events = []
    while True:
        try:
            event = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if event is None:
            graph_event_queues.pop(pc_id, None)
            return {"events": events, "closed": True}
        events.append(event)

    return {"events": events, "closed": False}


# ---------------------------------------------------------------------------
# Demo mode endpoints
# ---------------------------------------------------------------------------


@app.get("/api/demo/status")
async def demo_status():
    """Returns whether a demo session is currently active."""
    return {"active": demo_pc_id is not None, "event_count": len(demo_events)}


@app.get("/api/demo/poll")
async def demo_poll(cursor: int = 0):
    """Cursor-based poll for demo viewers. Returns new events since cursor."""
    if demo_pc_id is None:
        return {"events": [], "cursor": cursor, "active": False}
    new_events = demo_events[cursor:]
    return {"events": new_events, "cursor": len(demo_events), "active": True}


# ---------------------------------------------------------------------------
# Twilio phone integration
# ---------------------------------------------------------------------------


async def run_twilio_bot(websocket: WebSocket):
    """Run the GRC bot over a Twilio Media Stream WebSocket."""
    await websocket.accept()

    # Wait for the Twilio "start" event to get stream/call SIDs
    stream_sid = None
    call_sid = None
    async for raw in websocket.iter_text():
        msg = json.loads(raw)
        if msg.get("event") == "start":
            start = msg["start"]
            stream_sid = start["streamSid"]
            call_sid = start["callSid"]
            logger.info(f"Twilio call started — stream_sid={stream_sid} call_sid={call_sid}")
            break
        if msg.get("event") == "stop":
            logger.info("Twilio call stopped before start event")
            return

    if not stream_sid:
        logger.warning("No Twilio start event received")
        return

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=serializer,
        ),
    )

    stt = create_stt("elevenlabs")
    llm = create_llm("groq", system_instruction=SYSTEM_INSTRUCTION_GRC)
    tts = create_tts("elevenlabs")

    thinker_llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqLLMService.Settings(
            model="llama-3.1-8b-instant",
            extra={"response_format": {"type": "json_object"}},
        ),
    )
    thinker_processor = ThinkerProcessor(thinker_llm=thinker_llm)
    context_enricher = ContextEnricherProcessor(thinker_processor=thinker_processor)
    filler_tts = FillerTTSProcessor()
    lang_switch = LanguageSwitchProcessor(
        tts=tts,
        en_voice_id=os.getenv("ELEVENLABS_VOICE_ID", ""),
        multilingual_voice_id=os.getenv("ELEVENLABS_MULTILINGUAL_VOICE_ID", os.getenv("ELEVENLABS_VOICE_ID", "")),
    )

    # Register GRC tools
    async def handle_book_bulky_waste(params: FunctionCallParams):
        name = params.arguments.get("name", "").strip()
        phone = params.arguments.get("phone", "").strip()
        address = params.arguments.get("address", "").strip()
        preferred_date = params.arguments.get("preferred_date", "").strip()
        logger.info(f"[Twilio] book_bulky_waste({name}, {phone})")
        try:
            result = book_bulky_waste(
                {"name": name, "phone": phone, "address": address, "preferred_date": preferred_date}
            )
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"book_bulky_waste failed: {e}")
            await params.result_callback({"error": "Failed to book collection. Please try again."})

    async def handle_check_service_status(params: FunctionCallParams):
        phone = params.arguments.get("phone", "").strip()
        logger.info(f"[Twilio] check_service_status({phone})")
        try:
            result = check_service_status({"phone": phone})
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"check_service_status failed: {e}")
            await params.result_callback({"error": "Failed to check status. Please try again."})

    async def handle_update_booking_date(params: FunctionCallParams):
        phone = params.arguments.get("phone", "").strip()
        name = params.arguments.get("name", "").strip()
        new_date = params.arguments.get("new_date", "").strip()
        logger.info(f"[Twilio] update_booking_date({phone})")
        try:
            result = update_booking_date({"phone": phone, "name": name, "new_date": new_date})
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"update_booking_date failed: {e}")
            await params.result_callback({"error": "Failed to update booking. Please try again."})

    async def handle_get_bin_collection_day(params: FunctionCallParams):
        address = params.arguments.get("address", "").strip()
        logger.info(f"[Twilio] get_bin_collection_day({address})")
        try:
            result = await asyncio.to_thread(get_bin_collection_zone, {"address": address})
            await params.result_callback({"result": result})
        except Exception as e:
            logger.error(f"get_bin_collection_day failed: {e}")
            await params.result_callback(
                {"error": "I couldn't look up the bin collection day. Please try again."}
            )

    llm.register_function("book_bulky_waste", handle_book_bulky_waste)
    llm.register_function("check_service_status", handle_check_service_status)
    llm.register_function("update_booking_date", handle_update_booking_date)
    llm.register_function("get_bin_collection_day", handle_get_bin_collection_day)

    book_bulky_waste_schema = FunctionSchema(
        name="book_bulky_waste",
        description="Book a Bulky Waste Collection for a resident.",
        properties={
            "name": {"type": "string", "description": "Resident's full name"},
            "phone": {"type": "string", "description": "Resident's phone number"},
            "address": {"type": "string", "description": "Full property address"},
            "preferred_date": {"type": "string", "description": "Preferred collection date in YYYY-MM-DD format"},
        },
        required=["name", "phone", "address", "preferred_date"],
    )
    check_service_status_schema = FunctionSchema(
        name="check_service_status",
        description="Check how many bulky waste collections a resident has remaining this year.",
        properties={"phone": {"type": "string", "description": "Resident's phone number"}},
        required=["phone"],
    )
    update_booking_date_schema = FunctionSchema(
        name="update_booking_date",
        description="Change the date of an existing bulky waste booking.",
        properties={
            "phone": {"type": "string", "description": "Resident's phone number"},
            "name": {"type": "string", "description": "Resident's full name"},
            "new_date": {"type": "string", "description": "New preferred date in YYYY-MM-DD format"},
        },
        required=["phone", "name", "new_date"],
    )
    get_bin_collection_day_schema = FunctionSchema(
        name="get_bin_collection_day",
        description="Look up the bin collection day for a resident's address.",
        properties={
            "address": {"type": "string", "description": "Full street address within the Georges River LGA"},
        },
        required=["address"],
    )
    context = LLMContext(
        tools=ToolsSchema(
            standard_tools=[
                book_bulky_waste_schema,
                check_service_status_schema,
                update_booking_date_schema,
                get_bin_collection_day_schema,
            ]
        )
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            thinker_processor,
            lang_switch,
            user_aggregator,
            context_enricher,
            llm,
            filler_tts,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[LatencyObserver()],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Twilio client connected")
        context.add_message({
            "role": "system",
            "content": (
                "Greet the caller with: "
                "'Hi, I'm Maya from Georges River Council — how can I help you today?'"
            ),
        })
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Twilio client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


@app.post("/twilio/voice")
async def twilio_voice(request: Request):
    """Twilio webhook — returns TwiML that streams call audio to this server."""
    host = request.headers.get("host", "")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://{host}/twilio/ws" />
  </Connect>
</Response>"""
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/twilio/ws")
async def twilio_ws(websocket: WebSocket):
    """WebSocket endpoint for Twilio Media Streams."""
    await run_twilio_bot(websocket)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vocare Bot")
    parser.add_argument("--host", default="localhost", help="Host (default: localhost)")
    parser.add_argument("--port", type=int, default=7860, help="Port (default: 7860)")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
