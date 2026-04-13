# Live Transcript Feature Design

**Date:** 2026-04-13
**Status:** Approved

## Overview

Display a live conversation transcript between the user and the bot in the frontend, below the connect button in the left panel. Messages appear as chat bubbles after each turn completes (final only — no interim flickering). The transcript is scrollable and persists for the full session.

## Decisions

| Question | Decision |
|---|---|
| Layout position | Left panel, below connect button |
| Message style | Chat bubbles (user right/blue, bot left/dark) |
| Transcription mode | Final only — no interim/partial updates |
| History | Full scrollable session history |
| Architecture | Extend existing graph event queue (Option A) |

## Backend: TranscriptionObserver

A new `TranscriptionObserver` class added to `bot.py`, modeled on the existing `GraphHighlightObserver` pattern.

**Watched frames:**

- `TranscriptionFrame` — user's final transcription from STT. Emits immediately:
  ```json
  {"type": "user_transcription", "text": "..."}
  ```
- `LLMTextFrame` — accumulates bot response chunks internally.
- `LLMFullResponseEndFrame` — flushes the accumulated bot text and emits:
  ```json
  {"type": "bot_transcription", "text": "..."}
  ```

**Queue:** Both event types go into the existing `graph_event_queues[pc_id]`, drained by the existing `/api/graph/poll` endpoint every 250ms. No new endpoints or polling loops.

**Attachment:** `TranscriptionObserver` is instantiated alongside `GraphHighlightObserver` in the pipeline task setup, receiving the same `pc_id` and `event_queue` reference.

## Frontend: HTML & CSS

A `#transcript` section is added to the left panel in `static/index.html`, directly below the disconnect button / status indicator.

**Structure:**
```html
<div id="transcript" style="display:none;">
  <div class="transcript-label">TRANSCRIPT</div>
  <div id="transcriptMessages" class="transcript-messages"></div>
</div>
```

**Styling:**
- Container: hidden by default, shown on connect, cleared and hidden on disconnect
- Messages area: `overflow-y: auto`, `max-height: ~280px`, auto-scrolls to bottom on new message
- User bubble: right-aligned, `background: #1d4ed8`, white text, `border-radius: 12px 12px 2px 12px`
- Bot bubble: left-aligned, `background: #1e293b`, light text (`#e2e8f0`), `border-radius: 12px 12px 12px 2px`
- Both bubbles: `max-width: 80%`, `padding: 6px 10px`, `line-height: 1.5`

## Frontend: JavaScript

**`handleGraphEvent()` additions** (two new switch cases):

```javascript
case 'user_transcription':
  appendTranscriptBubble('user', ev.text);
  break;
case 'bot_transcription':
  appendTranscriptBubble('bot', ev.text);
  break;
```

**New helper function:**

```javascript
function appendTranscriptBubble(speaker, text) {
  const row = document.createElement('div');
  row.className = speaker === 'user' ? 'transcript-user' : 'transcript-bot';
  const bub = document.createElement('div');
  bub.className = 'bub';
  bub.textContent = text;
  row.appendChild(bub);
  document.getElementById('transcriptMessages').appendChild(row);
  // Auto-scroll to bottom
  const container = document.getElementById('transcriptMessages');
  container.scrollTop = container.scrollHeight;
}
```

**Connect/disconnect integration:**
- On connect: `document.getElementById('transcript').style.display = 'block'`
- On disconnect: hide transcript div and clear `#transcriptMessages` innerHTML

## Files Changed

| File | Change |
|---|---|
| `examples/vocare/bot.py` | Add `TranscriptionObserver` class; attach to pipeline task |
| `examples/vocare/static/index.html` | Add `#transcript` HTML + CSS; extend `handleGraphEvent()`; show/hide on connect/disconnect |

## Out of Scope

- Interim/partial transcription display
- Export or copy transcript
- Timestamps on messages
- Transcript persistence across sessions
