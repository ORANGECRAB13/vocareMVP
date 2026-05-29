# Vocare Foundry Pitch Demo

This folder runs the Foundry pitch version of Vocare: a real-time voice AI demo with Aria, a CommBank Premier Relationship Manager, and a live context graph traversal UI.

The frontend is designed for presenting:

- Phone: open the same URL, tap `Call Aria`, and speak to the agent.
- Laptop: open the same URL in `DEMO` mode and it mirrors the phone session graph/transcript for the room.

The graph shows the customer context Aria is accessing: verification, trusted device, card freeze, unusual transaction, payment impact, grace period, replacement card, and registered-address guardrails.

## What Runs

- `bot.py`: FastAPI server plus Pipecat voice pipeline.
- `static/index.html`: browser UI for phone and laptop.
- `static/graph-3d.js`: graph traversal, WebRTC call, demo mirror polling.
- `static/graph-3d.css`: dark Qantas-style graph presentation UI.
- `Dockerfile` and `docker-compose.yml`: containerized app and Neo4j sidecar.

Default local Python port: `7860`.

Default Docker browser port: `8090`.

## Requirements

You need:

- Python 3.11 recommended.
- Docker Desktop if using Docker.
- A modern Chromium-based browser.
- Microphone permission in the browser.
- API keys for the selected voice pipeline.
- Cloudflare Tunnel if you want to access the app from a phone over HTTPS.
- Twilio Network Traversal credentials are strongly recommended for phone/remote WebRTC.

## Environment

Create a `.env` file in this folder:

```powershell
copy .env.example .env
```

Fill in the keys you use:

```env
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MULTILINGUAL_VOICE_ID=
MISTRAL_API_KEY=
GROQ_API_KEY=
DEEPGRAM_API_KEY=

# Strongly recommended for phone/cloud tunnel WebRTC
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=

# Optional local graph sidecar
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=vocare2026
NEO4J_SEED=true
```

For this Foundry demo, the frontend graph has a local mock graph endpoint and does not require Neo4j to look good.

Voice calls need real provider keys. The current frontend requests:

- STT: ElevenLabs
- LLM: Mistral
- TTS: ElevenLabs

The background thinker also uses Groq in `bot.py`, so include `GROQ_API_KEY`.

## Run Locally With Python

From this folder:

```powershell
cd D:\vocare\v2\pipecat\examples\vocare
```

Install dependencies if needed:

```powershell
pip install uv
uv pip install --system "pipecat-ai[deepgram,elevenlabs,mistral,groq,silero,smallwebrtc]" fastapi uvicorn[standard] python-dotenv loguru cerebras-cloud-sdk neo4j aioice aiortc opencv-python-headless
```

Start the app:

```powershell
python bot.py --host 0.0.0.0 --port 7860
```

Open on the same machine:

```text
http://localhost:7860/
```

If you only want to inspect the graph UI without a real call, click `Run graph demo`.

## Run With Docker

From this folder:

```powershell
docker compose up --build
```

Open:

```text
http://localhost:8090/
```

Stop it:

```powershell
docker compose down
```

Docker notes:

- The app listens on `8080` inside the container.
- Compose publishes it to `8090` on your machine.
- `.env` is read by Compose but is not copied into the image.
- Neo4j runs as an internal sidecar service. Browser/Bolt ports are not published by default.

## Cloudflare Tunnel For Phone Access

Phone browsers usually need HTTPS for microphone access and WebRTC behaves better over a public HTTPS URL. Cloudflare Tunnel is the easiest way to expose your local app temporarily.

Install `cloudflared` if you do not already have it:

```powershell
winget install --id Cloudflare.cloudflared
```

Start the app first, either locally:

```powershell
python bot.py --host 0.0.0.0 --port 7860
```

or through Docker:

```powershell
docker compose up --build
```

Then start a tunnel.

For local Python:

```powershell
cloudflared tunnel --url http://localhost:7860
```

For Docker:

```powershell
cloudflared tunnel --url http://localhost:8090
```

Cloudflare prints a public URL like:

```text
https://something-random.trycloudflare.com
```

Use that exact URL on both phone and laptop.

## Phone + Laptop Presentation Mode

This is the intended demo setup.

1. Start the server locally or with Docker.
2. Start Cloudflare Tunnel.
3. Open the Cloudflare URL on the laptop first.
4. Leave the laptop in `DEMO` mode.
5. Put the laptop browser full-screen for the audience.
6. Open the same Cloudflare URL on the phone.
7. Leave the phone in `DEMO` mode.
8. On the phone, tap `Call Aria`.
9. Allow microphone permission.
10. Speak to Aria from the phone.

What happens:

- The phone becomes the demo presenter.
- The laptop automatically switches to `Watching live phone demo...`.
- Transcript events and graph node traversal are mirrored to the laptop.
- Audience sees the same graph traversal without needing to hear from the laptop mic.

If you do not see the laptop mirror:

- Confirm both devices are on the same Cloudflare URL.
- Confirm the laptop is in `DEMO`, not `INDIV`.
- Refresh the laptop page after the phone call starts.
- Check the server console for `/api/demo/status` and `/api/demo/poll` requests.

Use `INDIV` mode only when you want a single browser to own its own private call and not broadcast to demo viewers.

## Demo Conversation Script

Use this flow when presenting:

1. Aria greets Jack and asks him to approve the CommBank app push.
2. Jack says he approved it.
3. Aria verifies him and softly asks whether he is calling about the Visa credit card.
4. Jack says yes.
5. Aria reviews the frozen card and unusual electronics purchase.
6. Aria asks whether Jack made the purchase.
7. After Jack confirms, Aria can surface the payment impact.
8. Aria offers the grace period before applying it.
9. Aria offers the digital card before activating it.

The graph callouts are designed to appear as Aria accesses each relevant node.

## Troubleshooting

`Call Aria` fails immediately:

- Check `.env` has `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `MISTRAL_API_KEY`, and `GROQ_API_KEY`.
- Check the server terminal for provider errors.

Phone connects poorly or not at all through Cloudflare:

- Add `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` to `.env`.
- Restart the app after editing `.env`.
- The app requests Twilio TURN credentials from `/api/ice`.

Laptop mirror does not update:

- Laptop must be in `DEMO` mode.
- Phone must also be in `DEMO` mode before tapping `Call Aria`.
- Refresh laptop after the phone starts if it was opened late.

Graph appears but no real voice:

- `Run graph demo` only plays the frontend graph/tracing demo.
- A real call requires provider keys and microphone permission.

Docker shows old UI:

```powershell
docker compose build app
docker compose up -d --force-recreate app
```

Port already in use:

- Local Python default is `7860`.
- Docker publishes `8090`.
- Change the Python port with `--port`.
- Change Docker port mapping in `docker-compose.yml`.

## Useful Commands

Local:

```powershell
python bot.py --host 0.0.0.0 --port 7860
```

Docker:

```powershell
docker compose up --build
docker compose ps
docker compose logs -f app
docker compose down
```

Cloudflare:

```powershell
cloudflared tunnel --url http://localhost:7860
cloudflared tunnel --url http://localhost:8090
```

Git branch:

```powershell
git checkout foundry-pitch
```
