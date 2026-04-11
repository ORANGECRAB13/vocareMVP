# Vocare Voice Bot

A real-time voice AI agent built on [Pipecat](https://github.com/pipecat-ai/pipecat), featuring WebRTC transport, configurable STT/LLM/TTS services, and an optional Neo4j knowledge graph for proactive customer context.

## Features

- WebRTC audio/video via SmallWebRTC transport
- Configurable STT: Deepgram, ElevenLabs
- Configurable LLM: Mistral, Groq
- Configurable TTS: ElevenLabs
- Silero VAD (pre-loaded for low-latency session startup)
- Optional Neo4j knowledge graph with 3D graph visualization
- SSE-based real-time graph node highlighting as the bot speaks

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for Neo4j, optional)
- API keys for your chosen STT/LLM/TTS providers

## Setup

### 1. Install dependencies

From the repo root:

```bash
uv sync --group dev --all-extras --no-extra gstreamer
```

Or install just what the vocare example needs:

```bash
uv pip install pipecat-ai[deepgram,elevenlabs,mistral,groq,silero,smallwebrtc] fastapi uvicorn python-dotenv
```

### 2. Configure environment variables

Copy the root `env.example` to `examples/vocare/.env` and fill in your keys:

```bash
cp env.example examples/vocare/.env
```

Required keys (depending on which services you use):

```env
# STT
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...

# LLM
MISTRAL_API_KEY=...
GROQ_API_KEY=...

# TTS
ELEVENLABS_VOICE_ID=...   # ElevenLabs voice ID

# Neo4j (optional — enables knowledge graph mode)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=vocare2026
NEO4J_SEED=true            # set to true to populate demo data on startup
```

### 3. Start Neo4j (optional)

If you want the knowledge graph features:

```bash
cd examples/vocare
docker compose up -d
```

This starts Neo4j Community Edition on:
- Browser UI: http://localhost:7474
- Bolt: bolt://localhost:7687 (credentials: `neo4j` / `vocare2026`)

### 4. Run the bot server

```bash
cd examples/vocare
uv run python bot.py
```

The server starts at **http://localhost:8000**.

Open `http://localhost:8000` in your browser to launch the voice interface.

## Usage

The frontend lets you select STT, LLM, and TTS providers before connecting. Once connected, speak to the bot — the VAD detects speech automatically.

### Knowledge graph mode

When `NEO4J_URI` is set, the bot loads as a **Qantas customer service agent**. It can look up booking references, flight operations, baggage, and hotel/rebooking information from the graph. The 3D graph visualization highlights nodes in real time as the bot discusses them.

Demo booking reference: **QF-8842**

## Project structure

```
examples/vocare/
├── bot.py              # FastAPI server + Pipecat pipeline
├── knowledge_graph.py  # Neo4j seeding + query helpers
├── docker-compose.yml  # Neo4j service
└── static/
    └── index.html      # Browser frontend
```

## Architecture

```
Browser (WebRTC) ──► SmallWebRTCTransport
                         │
                    STTService (Deepgram / ElevenLabs)
                         │
                    LLMService (Mistral / Groq)  ──► Neo4j (optional)
                         │
                    TTSService (ElevenLabs)
                         │
                    SmallWebRTCTransport ──► Browser
```
