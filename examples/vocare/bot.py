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
from typing import Dict

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
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
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMRunFrame,
    LLMTextFrame,
    TTSSpeakFrame,
    TranscriptionFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

load_dotenv(override=True)

SYSTEM_INSTRUCTION_DEFAULT = (
    "You are a helpful assistant in a voice conversation. "
    "Your responses will be spoken aloud, so avoid emojis, bullet points, "
    "or other formatting that can't be spoken. "
    "Respond to what the user said in a creative, helpful, and brief way."
)

SYSTEM_INSTRUCTION_KG = (
    "You are a Qantas customer service agent on a voice call. "
    "Your name is Aria. Speak naturally, warmly, and briefly — one or two "
    "sentences at a time. "

    # --- Phase 1: Identity Collection ---
    "Start by asking for their name and flight number. "
    "Do not ask for a booking reference — passengers calling about cancellations "
    "rarely have it. "

    # --- Phase 2: Graph Lookup ---
    "Once you have their name and flight number, call lookup_customer immediately. "
    "Do not summarise anything before the tool returns data. "

    # --- Phase 3: Disruption Reveal ---
    "After retrieving their situation, the PRE-CALL BRIEF tells you exactly what "
    "happened and what is already arranged. "
    "Acknowledge the cancellation briefly and empathetically — explain the cause "
    "in ONE sentence. "
    "Then tell them the next available flight time. Do not over-explain. "

    # --- Phase 4: Confirm the rebook ---
    "The rescheduled flight is already identified in the brief. "
    "Tell the passenger the new departure time and ask if they want to confirm. "
    "Do NOT confirm without their verbal agreement. "

    # --- Phase 5: Baggage ---
    "If the passenger asks about their bags, call the lookup_baggage tool. "
    "Report the exact location — name the terminal, the carousel, and that the "
    "bag will automatically load onto the rescheduled flight. "
    "Be specific — use the detail from the data, not generic phrases. "

    # --- Phase 6: Accommodation ---
    "If the passenger asks about tonight or where to sleep, tell them: "
    "Qantas covers overnight accommodation for engineering delays. "
    "Rydges Airport Hotel has been booked and a room secured. "
    "An SMS with the digital hotel voucher and a fifty dollar meal allowance "
    "has already been sent to their phone. "
    "You do not need to ask them — just confirm it is done. "

    # --- Tone ---
    "Always be human, concise, and proactive. Never read out lists. "
    "Do not use filler phrases like 'Certainly!' or 'Of course!'. "
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


def create_llm(name: str, system_instruction: str = SYSTEM_INSTRUCTION_DEFAULT):
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


neo4j_driver = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global neo4j_driver

    # Pre-load Silero VAD ONNX session once (avoids 50–250ms load per session).
    # The InferenceSession is stateless and safe to share; each SileroVADAnalyzer
    # still gets its own mutable state (_model._state, _context, etc.).
    from pipecat.audio.vad.silero import SileroOnnxModel

    _warmup_vad = SileroVADAnalyzer()
    _cached_session = _warmup_vad._model.session
    _orig_init = SileroOnnxModel.__init__

    def _fast_init(self, path, force_onnx_cpu=True):
        self.session = _cached_session
        self.reset_states()
        self.sample_rates = [8000, 16000]

    SileroOnnxModel.__init__ = _fast_init
    logger.info("Silero VAD ONNX session pre-loaded")

    # Initialize Neo4j driver if configured
    neo4j_uri = os.getenv("NEO4J_URI")
    if neo4j_uri:
        try:
            from neo4j import GraphDatabase

            from knowledge_graph import seed_graph

            neo4j_driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(
                    os.getenv("NEO4J_USERNAME", "neo4j"),
                    os.getenv("NEO4J_PASSWORD", ""),
                ),
            )
            neo4j_driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {neo4j_uri}")

            if os.getenv("NEO4J_SEED", "").lower() == "true":
                seed_graph(neo4j_driver)
        except Exception as e:
            logger.warning(f"Neo4j not available: {e}. Knowledge graph features disabled.")
            neo4j_driver = None

    yield

    coros = [pc.disconnect() for pc in pcs_map.values()]
    await asyncio.gather(*coros)
    pcs_map.clear()

    if neo4j_driver:
        neo4j_driver.close()
        logger.info("Neo4j driver closed")


app = FastAPI(lifespan=lifespan)


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


class GraphHighlightObserver(BaseObserver):
    """Watches LLM text output and highlights graph nodes being discussed.

    Accumulates LLM text chunks and scans for keywords that map to graph
    node IDs. When a match is found, pushes a highlight event to the SSE
    queue so the frontend can pulse the relevant node.
    """

    def __init__(self, event_queue: asyncio.Queue):
        super().__init__()
        self._keyword_map: Dict[str, str] = {}
        self._sorted_keywords: list = []
        self._event_queue = event_queue
        self._buffer = ""
        self._last_highlight = ""
        self._last_highlight_time = 0.0

    def set_keyword_map(self, keyword_map: Dict[str, str]):
        """Update the keyword map once the graph structure is available."""
        self._keyword_map = keyword_map
        self._sorted_keywords = sorted(keyword_map.keys(), key=len, reverse=True)

    async def on_push_frame(self, data: FramePushed):
        if (
            not isinstance(data.frame, LLMTextFrame)
            or data.direction != FrameDirection.DOWNSTREAM
            or not isinstance(data.source, LLMService)
        ):
            return

        self._buffer += data.frame.text

        # Scan buffer for keyword matches (check every few chars to avoid excess work)
        if len(self._buffer) < 4:
            return

        buf_lower = self._buffer.lower()
        for keyword in self._sorted_keywords:
            if keyword in buf_lower:
                node_id = self._keyword_map[keyword]
                now = asyncio.get_event_loop().time()
                # Debounce: don't re-highlight the same node within 2 seconds
                if node_id != self._last_highlight or (now - self._last_highlight_time) > 2.0:
                    self._last_highlight = node_id
                    self._last_highlight_time = now
                    event = {"type": "highlight", "nodeId": node_id}
                    try:
                        self._event_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        pass
                    if demo_pc_id is not None:
                        demo_events.append(event)
                # Trim buffer to keep only the last few chars (for partial word overlap)
                self._buffer = self._buffer[-10:]
                return

        # Keep buffer from growing unbounded
        if len(self._buffer) > 100:
            self._buffer = self._buffer[-20:]


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
# Bot pipeline
# ---------------------------------------------------------------------------


async def run_bot(
    webrtc_connection: SmallWebRTCConnection,
    stt_name: str,
    llm_name: str,
    tts_name: str,
    use_kg: bool = False,
):
    logger.info(f"Starting bot — STT={stt_name}, LLM={llm_name}, TTS={tts_name}")
    if use_kg:
        logger.info("Knowledge graph enabled — agent will ask for booking details")

    system_instruction = SYSTEM_INSTRUCTION_KG if use_kg else SYSTEM_INSTRUCTION_DEFAULT

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

    # Attach pipeline observers: transcript (always) and graph highlight (KG sessions only)
    pc_id = webrtc_connection.pc_id
    event_queue = graph_event_queues.get(pc_id)
    observers = []
    highlight_observer = None
    if event_queue:
        transcript_observer = TranscriptionObserver(event_queue)
        observers.append(transcript_observer)
    if use_kg and event_queue:
        highlight_observer = GraphHighlightObserver(event_queue)
        observers.append(highlight_observer)

    # --- KG function tools (registered on LLM when KG is enabled) ---

    async def _load_graph_and_context(booking_ref: str) -> str:
        """Shared helper: query Neo4j, send graph to frontend, return context."""
        from knowledge_graph import (
            build_keyword_map,
            build_traversal_sequence,
            query_customer_context,
            query_graph_structure,
        )

        graph_structure, kg_context = await asyncio.gather(
            query_graph_structure(neo4j_driver, booking_ref),
            query_customer_context(neo4j_driver, booking_ref),
        )

        # Send graph visualization to frontend
        if event_queue and graph_structure:
            await _put_graph_event(event_queue, {"type": "graph", "data": graph_structure})
            traversal = build_traversal_sequence(graph_structure)

            async def _animate():
                for evt in traversal:
                    await asyncio.sleep(0.35)
                    await _put_graph_event(event_queue, evt)
                await _put_graph_event(event_queue, {"type": "context_loaded"})

            asyncio.create_task(_animate())

            if highlight_observer:
                kw_map = build_keyword_map(graph_structure)
                highlight_observer.set_keyword_map(kw_map)
                logger.info(f"Graph highlight observer: {len(kw_map)} keywords mapped")

        return kg_context or ""

    async def handle_lookup_booking(params: FunctionCallParams):
        """Look up a customer by booking reference number."""
        booking_ref = params.arguments.get("booking_ref", "").strip()
        logger.info(f"Function call: lookup_booking({booking_ref})")

        if not neo4j_driver:
            await params.result_callback(
                {"error": "System unavailable, please try again later."}
            )
            return

        try:
            kg_context = await _load_graph_and_context(booking_ref)
            if kg_context:
                await params.result_callback({"customer_context": kg_context})
            else:
                await params.result_callback(
                    {"error": f"No booking found for reference {booking_ref}. "
                     "Ask the customer to double-check, or ask for their name "
                     "and flight route instead."}
                )
        except Exception as e:
            logger.error(f"lookup_booking failed: {e}")
            await params.result_callback(
                {"error": "Failed to look up booking. Please try again."}
            )

    async def handle_lookup_customer(params: FunctionCallParams):
        """Look up a customer by name and flight route."""
        name = params.arguments.get("customer_name", "").strip()
        route = params.arguments.get("flight_route", "").strip()
        logger.info(f"Function call: lookup_customer({name}, {route})")

        if not neo4j_driver:
            await params.result_callback(
                {"error": "System unavailable, please try again later."}
            )
            return

        try:
            from knowledge_graph import query_booking_by_name_and_route

            booking_ref = await query_booking_by_name_and_route(
                neo4j_driver, name, route
            )
            if booking_ref:
                kg_context = await _load_graph_and_context(booking_ref)
                if kg_context:
                    await params.result_callback({"customer_context": kg_context})
                    return

            await params.result_callback(
                {"error": f"No customer found matching name '{name}' and route '{route}'. "
                 "Ask the customer to clarify their details."}
            )
        except Exception as e:
            logger.error(f"lookup_customer failed: {e}")
            await params.result_callback(
                {"error": "Failed to look up customer. Please try again."}
            )

    async def handle_lookup_baggage(params: FunctionCallParams):
        """Retrieve baggage status and highlight all bag nodes on the frontend graph."""
        booking_ref = params.arguments.get("booking_ref", "").strip()
        logger.info(f"Function call: lookup_baggage({booking_ref})")

        if not neo4j_driver:
            await params.result_callback(
                {"error": "System unavailable, please try again later."}
            )
            return

        try:
            from knowledge_graph import query_baggage_context

            result = await query_baggage_context(neo4j_driver, booking_ref)
            if result:
                if event_queue:
                    for node_id in result["node_ids"]:
                        await _put_graph_event(
                            event_queue, {"type": "highlight", "nodeId": node_id}
                        )
                await params.result_callback({"baggage": result["summary"]})
            else:
                await params.result_callback(
                    {"error": f"No baggage found for booking {booking_ref}."}
                )
        except Exception as e:
            logger.error(f"lookup_baggage failed: {e}")
            await params.result_callback(
                {"error": "Failed to retrieve baggage info. Please try again."}
            )

    # Register tools on the LLM and build schema
    tools = None
    if use_kg:
        llm.register_function("lookup_booking", handle_lookup_booking)
        llm.register_function("lookup_customer", handle_lookup_customer)
        llm.register_function("lookup_baggage", handle_lookup_baggage)

        @llm.event_handler("on_function_calls_started")
        async def on_function_calls_started(service, function_calls):
            await tts.queue_frame(TTSSpeakFrame("Let me pull up your details."))

        lookup_baggage_schema = FunctionSchema(
            name="lookup_baggage",
            description=(
                "Retrieve baggage status for a booking — count, tag numbers, weight, "
                "and whether bags have been automatically transferred to the alternative flight. "
                "Call this when the passenger asks about their bags or luggage."
            ),
            properties={
                "booking_ref": {
                    "type": "string",
                    "description": "The booking reference, e.g. QF-8200",
                },
            },
            required=["booking_ref"],
        )
        lookup_booking_schema = FunctionSchema(
            name="lookup_booking",
            description=(
                "Look up a customer's full situation by their booking reference number. "
                "Call this when the customer provides a booking reference like QF-8200."
            ),
            properties={
                "booking_ref": {
                    "type": "string",
                    "description": "The booking reference number, e.g. QF-8200",
                },
            },
            required=["booking_ref"],
        )
        lookup_customer_schema = FunctionSchema(
            name="lookup_customer",
            description=(
                "Look up a customer by their name and flight number or route. "
                "Call this when the customer provides their name and flight details "
                "instead of a booking reference. Accepts flight numbers like 'QF82' "
                "or route codes like 'SYD-MEL'."
            ),
            properties={
                "customer_name": {
                    "type": "string",
                    "description": "The customer's full name, e.g. Jack Smith",
                },
                "flight_route": {
                    "type": "string",
                    "description": (
                        "The flight number (e.g. 'QF82'), route codes (e.g. 'SYD-MEL'), "
                        "or city names (e.g. 'Sydney to Melbourne')"
                    ),
                },
            },
            required=["customer_name", "flight_route"],
        )
        tools = ToolsSchema(
            standard_tools=[lookup_booking_schema, lookup_customer_schema, lookup_baggage_schema]
        )

    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
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

        if use_kg:
            context.add_message(
                {
                    "role": "system",
                    "content": (
                        "Greet the caller warmly as Aria, a Qantas service agent. "
                        "Ask for their name and flight number so you can pull up "
                        "their details."
                    ),
                }
            )
        else:
            context.add_message(
                {"role": "system", "content": "Please introduce yourself to the user."}
            )

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
    stt_name = request.get("stt", "deepgram")
    llm_name = request.get("llm", "groq")
    tts_name = request.get("tts", "elevenlabs")
    use_kg = request.get("use_kg", False)
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
            run_bot, pipecat_connection, stt_name, llm_name, tts_name, use_kg
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
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vocare Bot")
    parser.add_argument("--host", default="localhost", help="Host (default: localhost)")
    parser.add_argument("--port", type=int, default=7860, help="Port (default: 7860)")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
