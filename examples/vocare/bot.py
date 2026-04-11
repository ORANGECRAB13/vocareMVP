"""Vocare voice bot with configurable STT/LLM/TTS via WebRTC transport.

The frontend sends service selections (stt, llm, tts) as part of the
/api/offer request body. The bot dynamically creates the chosen services
for each session.
"""

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Dict

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, LLMTextFrame, TTSSpeakFrame
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
from pipecat.services.ai_services import LLMService
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
    "You are a Qantas customer service agent in a voice call. "
    "Start by warmly greeting the caller and asking for their booking reference number. "
    "If they don't know it, ask for their name and original flight route so you can look it up. "
    "Once you have their details, use the appropriate lookup tool to retrieve their information. "
    "After retrieving their situation, acknowledge what happened, show empathy, "
    "and proactively offer solutions. Speak naturally and briefly."
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

ice_servers = [
    IceServer(urls="stun:stun.l.google.com:19302"),
]


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
                    try:
                        self._event_queue.put_nowait(
                            {"type": "highlight", "nodeId": node_id}
                        )
                    except asyncio.QueueFull:
                        pass
                # Trim buffer to keep only the last few chars (for partial word overlap)
                self._buffer = self._buffer[-10:]
                return

        # Keep buffer from growing unbounded
        if len(self._buffer) > 100:
            self._buffer = self._buffer[-20:]


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

    # Create graph highlight observer (keyword map populated after graph lookup)
    pc_id = webrtc_connection.pc_id
    event_queue = graph_event_queues.get(pc_id)
    observers = []
    highlight_observer = None
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
            await event_queue.put({"type": "graph", "data": graph_structure})
            traversal = build_traversal_sequence(graph_structure)

            async def _animate():
                for evt in traversal:
                    await asyncio.sleep(0.35)
                    await event_queue.put(evt)
                await event_queue.put({"type": "context_loaded"})

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

    # Register tools on the LLM and build schema
    tools = None
    if use_kg:
        llm.register_function("lookup_booking", handle_lookup_booking)
        llm.register_function("lookup_customer", handle_lookup_customer)

        @llm.event_handler("on_function_calls_started")
        async def on_function_calls_started(service, function_calls):
            await tts.queue_frame(TTSSpeakFrame("Let me pull up your details."))

        lookup_booking_schema = FunctionSchema(
            name="lookup_booking",
            description=(
                "Look up a customer's full situation by their booking reference number. "
                "Call this when the customer provides a booking reference like QF-8842."
            ),
            properties={
                "booking_ref": {
                    "type": "string",
                    "description": "The booking reference number, e.g. QF-8842",
                },
            },
            required=["booking_ref"],
        )
        lookup_customer_schema = FunctionSchema(
            name="lookup_customer",
            description=(
                "Look up a customer by their name and original flight route. "
                "Call this when the customer doesn't know their booking reference "
                "but provides their name and flight details."
            ),
            properties={
                "customer_name": {
                    "type": "string",
                    "description": "The customer's full name, e.g. Sarah Mitchell",
                },
                "flight_route": {
                    "type": "string",
                    "description": (
                        "The flight route using city names or airport codes, "
                        "e.g. 'Sydney to Auckland' or 'SYD-AKL'"
                    ),
                },
            },
            required=["customer_name", "flight_route"],
        )
        tools = ToolsSchema(
            standard_tools=[lookup_booking_schema, lookup_customer_schema]
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
                        "Greet the caller warmly as a Qantas agent. Ask for their "
                        "booking reference number. If they don't have it, let them know "
                        "you can also look them up by name and flight route."
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
        logger.info("Client disconnected")
        pc_id = webrtc_connection.pc_id
        queue = graph_event_queues.pop(pc_id, None)
        if queue:
            await queue.put(None)  # Signal SSE to close
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


@app.post("/api/offer")
async def offer(request: dict, background_tasks: BackgroundTasks):
    pc_id = request.get("pc_id")

    # Extract service selections (defaults if not provided)
    stt_name = request.get("stt", "deepgram")
    llm_name = request.get("llm", "groq")
    tts_name = request.get("tts", "elevenlabs")
    use_kg = request.get("use_kg", False)

    if pc_id and pc_id in pcs_map:
        pipecat_connection = pcs_map[pc_id]
        logger.info(f"Reusing existing connection for pc_id: {pc_id}")
        await pipecat_connection.renegotiate(
            sdp=request["sdp"],
            type=request["type"],
            restart_pc=request.get("restart_pc", False),
        )
    else:
        pipecat_connection = SmallWebRTCConnection(ice_servers)
        await pipecat_connection.initialize(sdp=request["sdp"], type=request["type"])

        @pipecat_connection.event_handler("closed")
        async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
            logger.info(f"Discarding peer connection for pc_id: {webrtc_connection.pc_id}")
            pcs_map.pop(webrtc_connection.pc_id, None)

        background_tasks.add_task(
            run_bot, pipecat_connection, stt_name, llm_name, tts_name, use_kg
        )

    answer = pipecat_connection.get_answer()
    pc_id_value = answer["pc_id"]
    pcs_map[pc_id_value] = pipecat_connection

    # Create SSE event queue for graph traversal if KG enabled
    if use_kg:
        graph_event_queues[pc_id_value] = asyncio.Queue()

    return answer


@app.get("/api/graph/events/{pc_id:path}")
async def graph_events(pc_id: str):
    """SSE endpoint streaming live graph traversal events for a session."""
    logger.info(f"SSE connection requested for pc_id: {pc_id}")
    logger.info(f"Available queues: {list(graph_event_queues.keys())}")

    queue = graph_event_queues.get(pc_id)

    if not queue:
        # Retry briefly — queue may not be registered yet due to timing
        for _ in range(10):
            await asyncio.sleep(0.2)
            queue = graph_event_queues.get(pc_id)
            if queue:
                break

    if not queue:
        logger.warning(f"No graph event queue found for pc_id: {pc_id}")
        return StreamingResponse(
            iter(["data: {\"type\": \"error\", \"message\": \"No session found\"}\n\n"]),
            media_type="text/event-stream",
        )

    logger.info(f"SSE stream started for pc_id: {pc_id}")

    async def event_stream():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            graph_event_queues.pop(pc_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vocare Bot")
    parser.add_argument("--host", default="localhost", help="Host (default: localhost)")
    parser.add_argument("--port", type=int, default=7860, help="Port (default: 7860)")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
