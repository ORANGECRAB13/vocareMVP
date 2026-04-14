# Live Transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a scrollable live chat-bubble transcript of the conversation (user + bot) in the left panel below the connect button.

**Architecture:** A new `TranscriptionObserver` in `bot.py` watches `TranscriptionFrame` (user speech) and `LLMTextFrame`/`LLMFullResponseEndFrame` (bot response), pushing events into the existing `graph_event_queues` queue. The frontend's existing 250ms polling loop picks these up via the existing `/api/graph/poll` endpoint and renders chat bubbles in a new `#transcript` panel.

**Tech Stack:** Python (pipecat observers), vanilla JavaScript, CSS in a monolithic `static/index.html`

---

## File Map

| File | Change |
|---|---|
| `examples/vocare/bot.py` | Add `TranscriptionObserver` class; import 2 new frame types; always create event queue; always attach observer |
| `examples/vocare/static/index.html` | Add CSS for transcript panel; add HTML div; extend `handleGraphEvent()`; show/hide on connect/disconnect; always start polling |

---

## Task 1: Add TranscriptionObserver to bot.py

**Files:**
- Modify: `examples/vocare/bot.py:137` (imports)
- Modify: `examples/vocare/bot.py:377–436` (after `GraphHighlightObserver` class)
- Modify: `examples/vocare/bot.py:469–475` (observer setup in `run_bot`)
- Modify: `examples/vocare/bot.py:786–788` (event queue creation in `/api/offer`)

- [ ] **Step 1: Add missing frame imports**

Open `examples/vocare/bot.py`. Find line 137:
```python
from pipecat.frames.frames import LLMRunFrame, LLMTextFrame, TTSSpeakFrame
```
Replace with:
```python
from pipecat.frames.frames import LLMFullResponseEndFrame, LLMRunFrame, LLMTextFrame, TTSSpeakFrame, TranscriptionFrame
```

- [ ] **Step 2: Add TranscriptionObserver class**

In `examples/vocare/bot.py`, find the end of the `GraphHighlightObserver` class (around line 435, the last method `on_push_frame`). Add the new class immediately after it, before the `# ---------------------------------------------------------------------------\n# Bot pipeline` comment:

```python
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
                event = {"type": "user_transcription", "text": text}
                try:
                    self._event_queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
                if demo_pc_id is not None:
                    demo_events.append(event)

        elif isinstance(frame, LLMTextFrame) and isinstance(data.source, LLMService):
            self._bot_buffer += frame.text

        elif isinstance(frame, LLMFullResponseEndFrame):
            text = self._bot_buffer.strip()
            self._bot_buffer = ""
            if text:
                event = {"type": "bot_transcription", "text": text}
                try:
                    self._event_queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
                if demo_pc_id is not None:
                    demo_events.append(event)
```

- [ ] **Step 3: Always attach TranscriptionObserver in run_bot**

In `run_bot`, find the observer setup block (around lines 468–475):
```python
    pc_id = webrtc_connection.pc_id
    event_queue = graph_event_queues.get(pc_id)
    observers = []
    highlight_observer = None
    if use_kg and event_queue:
        highlight_observer = GraphHighlightObserver(event_queue)
        observers.append(highlight_observer)
```
Replace with:
```python
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
```

- [ ] **Step 4: Always create event queue in /api/offer**

In the `/api/offer` route, find the event queue creation block (around lines 786–788):
```python
    # Create SSE event queue for graph traversal if KG enabled
    if use_kg:
        graph_event_queues[pc_id_value] = asyncio.Queue()
```
Replace with:
```python
    # Create SSE event queue for transcript and graph events
    graph_event_queues[pc_id_value] = asyncio.Queue()
```

- [ ] **Step 5: Verify the changes look correct**

Run:
```bash
cd D:/vocare/v2/pipecat/examples/vocare
python -c "import ast, sys; ast.parse(open('bot.py').read()); print('Syntax OK')"
```
Expected output: `Syntax OK`

- [ ] **Step 6: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/bot.py
git commit -m "feat: add TranscriptionObserver for live transcript events"
```

---

## Task 2: Add transcript panel HTML and CSS

**Files:**
- Modify: `examples/vocare/static/index.html:7–430` (CSS block)
- Modify: `examples/vocare/static/index.html:488` (HTML, after `#status` div)

- [ ] **Step 1: Add CSS for transcript panel**

In `examples/vocare/static/index.html`, find the closing `</style>` tag (line 430). Insert these styles immediately before it:

```css
    /* Transcript panel */
    #transcript {
      display: none;
      margin-top: 1rem;
      flex-shrink: 0;
    }

    .transcript-label {
      font-size: 0.7rem;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #555;
      margin-bottom: 0.5rem;
    }

    .transcript-messages {
      max-height: 280px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    /* Hide scrollbar but keep scrollability */
    .transcript-messages::-webkit-scrollbar { width: 4px; }
    .transcript-messages::-webkit-scrollbar-track { background: transparent; }
    .transcript-messages::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }

    .transcript-user,
    .transcript-bot {
      display: flex;
    }

    .transcript-user { justify-content: flex-end; }
    .transcript-bot  { justify-content: flex-start; }

    .transcript-user .transcript-bub {
      background: #1d4ed8;
      color: #fff;
      border-radius: 12px 12px 2px 12px;
    }

    .transcript-bot .transcript-bub {
      background: #1e293b;
      color: #e2e8f0;
      border-radius: 12px 12px 12px 2px;
    }

    .transcript-bub {
      padding: 6px 10px;
      max-width: 80%;
      font-size: 0.82rem;
      line-height: 1.5;
      word-break: break-word;
    }
```

- [ ] **Step 2: Add transcript div to HTML**

Find the `#status` div (line 488):
```html
      <div id="status"></div>
    </div>
```
Replace with:
```html
      <div id="status"></div>

      <div id="transcript">
        <div class="transcript-label">Transcript</div>
        <div id="transcriptMessages" class="transcript-messages"></div>
      </div>
    </div>
```

- [ ] **Step 3: Verify the page loads without errors**

Start the server and open http://localhost:7860 in a browser. Open the browser console — there should be no errors. The transcript div is hidden so visually nothing changes yet.

- [ ] **Step 4: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/static/index.html
git commit -m "feat: add transcript panel HTML and CSS to left panel"
```

---

## Task 3: Wire up transcript JavaScript

**Files:**
- Modify: `examples/vocare/static/index.html:656–675` (`handleGraphEvent` function)
- Modify: `examples/vocare/static/index.html:596–605` (`pc.onconnectionstatechange`)
- Modify: `examples/vocare/static/index.html:643–646` (graph SSE start, inside `connect()`)
- Modify: `examples/vocare/static/index.html:814–835` (`cleanup` function)

- [ ] **Step 1: Add appendTranscriptBubble helper function**

In `static/index.html`, find the line:
```javascript
    // Shared graph event handler — used by both presenter poll and viewer poll
    function handleGraphEvent(event) {
```
Insert the new helper function immediately before it:
```javascript
    function appendTranscriptBubble(speaker, text) {
      const messages = document.getElementById('transcriptMessages');
      const row = document.createElement('div');
      row.className = speaker === 'user' ? 'transcript-user' : 'transcript-bot';
      const bub = document.createElement('div');
      bub.className = 'transcript-bub';
      bub.textContent = text;
      row.appendChild(bub);
      messages.appendChild(row);
      messages.scrollTop = messages.scrollHeight;
    }

```

- [ ] **Step 2: Add transcript cases to handleGraphEvent**

Find the end of `handleGraphEvent`:
```javascript
      } else if (event.type === 'highlight') {
        graphRenderer.highlightNode(event.nodeId);
      }
    }
```
Replace with:
```javascript
      } else if (event.type === 'highlight') {
        graphRenderer.highlightNode(event.nodeId);
      } else if (event.type === 'user_transcription') {
        appendTranscriptBubble('user', event.text);
      } else if (event.type === 'bot_transcription') {
        appendTranscriptBubble('bot', event.text);
      }
    }
```

- [ ] **Step 3: Always start graph/transcript polling after connect**

Find inside `connect()`:
```javascript
        // Start polling for graph events
        if (useKg) {
          connectGraphSSE(pcId);
        }
```
Replace with:
```javascript
        // Start polling for graph and transcript events
        connectGraphSSE(pcId);
```

- [ ] **Step 4: Show transcript on connected state**

Find inside `pc.onconnectionstatechange`:
```javascript
          if (pc.connectionState === 'connected') {
            setStatus('Connected', 'connected');
            audioIndicator.classList.add('active');
            disconnectBtn.style.display = 'block';
```
Replace with:
```javascript
          if (pc.connectionState === 'connected') {
            setStatus('Connected', 'connected');
            audioIndicator.classList.add('active');
            disconnectBtn.style.display = 'block';
            document.getElementById('transcript').style.display = 'block';
```

- [ ] **Step 5: Clear and hide transcript on cleanup**

Find inside `cleanup()`:
```javascript
      connectBtn.disabled = false;
      connectBtn.style.display = 'block';
      disconnectBtn.style.display = 'none';
      controlsSection.style.display = '';
```
Replace with:
```javascript
      connectBtn.disabled = false;
      connectBtn.style.display = 'block';
      disconnectBtn.style.display = 'none';
      controlsSection.style.display = '';
      document.getElementById('transcript').style.display = 'none';
      document.getElementById('transcriptMessages').innerHTML = '';
```

- [ ] **Step 6: Manual smoke test**

1. Start the bot: `cd D:/vocare/v2/pipecat/examples/vocare && python bot.py`
2. Open http://localhost:7860
3. Click Connect and speak a sentence
4. Verify: a blue right-aligned bubble appears with your transcribed words
5. Verify: after the bot responds, a dark left-aligned bubble appears with the bot's full reply
6. Verify: the panel scrolls to the latest message automatically
7. Click Disconnect — verify the transcript panel disappears and is empty on next connect

- [ ] **Step 7: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/static/index.html
git commit -m "feat: wire transcript JS — bubbles on user/bot transcription events"
```
