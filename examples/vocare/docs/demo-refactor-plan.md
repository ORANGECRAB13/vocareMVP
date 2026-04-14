# Vocare Demo: Qantas Cascading Disruption — Refactor Plan (Repo-Aligned)

## Scenario Summary

**Passenger:** Von
**Booking ref:** QF-7731
**Route:** SYD → GUM → HNL → SFO
**Situation:** QF107 SYD→GUM cancelled (hydraulic fault on VH-OQF). This cascades to disrupt
the QF821 GUM→HNL connection. Agent surfaces both, presents options, does NOT auto-rebook.
When Von asks about baggage, the graph highlights all 4 bag nodes showing auto-transfer to QF109.

---

## 1. Agent System Instruction Refactor

### `SYSTEM_INSTRUCTION_KG` in `bot.py`

```python
SYSTEM_INSTRUCTION_KG = (
    "You are a Qantas customer service agent on a voice call. "
    "Your name is Aria. Speak naturally, warmly, and briefly — never read out long lists. "

    # --- Phase 1: Identity Collection ---
    "Start by warmly greeting the caller and asking for their booking reference number. "
    "If they don't have it, ask for their name and original flight route so you can look them up. "

    # --- Phase 2: Graph Lookup ---
    "Once you have their details, call the appropriate lookup tool immediately. "
    "Do not summarise anything before the tool returns data. "

    # --- Phase 3: Disruption Reveal ---
    "After retrieving their situation, acknowledge the disruption briefly and empathetically. "
    "Explain the cause in ONE sentence only (e.g. maintenance hold on the aircraft). "
    "Then immediately surface the downstream impact: if a connecting flight is also disrupted, "
    "name that leg specifically. Do not over-explain. "

    # --- Phase 4: Options (DO NOT REBOOK) ---
    "Do NOT confirm any rebooking automatically. "
    "Present 2–3 concrete options clearly. Each option should include the new flight time, "
    "routing, and any upgrade or compensation attached. "
    "Ask the passenger which option they prefer before taking any action. "

    # --- Phase 5: Baggage Handling ---
    "If the passenger asks about their baggage, call the lookup_baggage tool immediately. "
    "Confirm the exact number of checked bags and whether they have been automatically "
    "transferred to the alternative flight. Be specific — name the bag count. "

    # --- Tone ---
    "Always be human, concise, and proactive. Never list more than 3 items in one breath. "
    "Do not use filler phrases like 'Certainly!' or 'Of course!'. "
)
```

### On-Connect Injected System Message in `bot.py`

```python
# Inside on_client_connected handler (replaces the existing KG injection):
context.add_message({
    "role": "system",
    "content": (
        "Greet the caller warmly as Aria, a Qantas service agent. "
        "Ask for their booking reference number. "
        "If they don't have it, let them know you can look them up by name and flight route."
    )
})
```

---

## 2. Knowledge Graph — Node & Edge Schema

### Node types used (must match existing frontend TYPE_COLORS in `index.html`)

| Plan concept | Maps to existing node type | Frontend colour |
|---|---|---|
| Passenger / Customer | `Customer` | Amber `#f59e0b` |
| Flight leg (any status) | `FlightOperation` | Blue `#3b82f6` |
| Checked bag | `Baggage` | Green `#10b981` |
| Alternative flight / rebooking option | `Rebooking` | Purple `#8b5cf6` |
| Compensation / upgrade note | fold into `Rebooking` sublabel | — |
| Communications | `Communication` | Orange `#f97316` |

> **Drop from plan:** `Aircraft`, `Connection`, `AlternativeFlight`, `CompensationOffer` as
> separate node types. Fold aircraft fault into `FlightOperation` sublabel.
> Fold upgrade eligibility into `Rebooking` sublabel.

### Edges (use existing relationship labels that the frontend traversal already handles)

```
(Customer)-[:HAS_FLIGHT]->(FlightOperation QF107 SYD→GUM)   # CANCELLED
(Customer)-[:HAS_FLIGHT]->(FlightOperation QF821 GUM→HNL)   # DISRUPTED
(Customer)-[:HAS_FLIGHT]->(FlightOperation QF815 HNL→SFO)   # UNAFFECTED
(Customer)-[:HAS_BAGGAGE]->(Baggage) x4
(Customer)-[:HAS_REBOOKING_OPTION]->(Rebooking QF109)
(Baggage x4)-[:CHECKED_ON]->(FlightOperation QF107)          # existing edge type
```

> `CHECKED_ON` edges to QF107 are correct — bags were checked on the cancelled leg.
> After agent confirms rebooking, bags are logically re-tagged to QF109 but the graph
> doesn't need a separate edge for the demo (bag nodes pulse green to signal "safe").

### Seed data for Von — `knowledge_graph.py` `seed_graph()`

Replace the existing Sarah Mitchell / QF-8842 MERGE block with:

```python
session.run("""
    // Customer
    MERGE (c:Customer {booking_ref: 'QF-7731'})
    SET c.name = 'Von',
        c.phone = '+61400000000',
        c.loyalty_tier = 'Gold'

    // Leg 1 — CANCELLED (cause: hydraulic fault)
    MERGE (f1:FlightOperation {flight_number: 'QF107'})
    SET f1.route = 'SYD-GUM',
        f1.status = 'CANCELLED',
        f1.reason = 'hydraulic fault on VH-OQF',
        f1.scheduled_time = '2026-04-14T08:30',
        f1.description = 'Sydney to Guam, cancelled due to maintenance hold'

    // Leg 2 — DISRUPTED (missed connection)
    MERGE (f2:FlightOperation {flight_number: 'QF821'})
    SET f2.route = 'GUM-HNL',
        f2.status = 'DISRUPTED',
        f2.reason = 'missed connection due to QF107 cancellation',
        f2.scheduled_time = '2026-04-14T14:15',
        f2.description = 'Guam to Honolulu, disrupted by upstream cancellation'

    // Leg 3 — UNAFFECTED
    MERGE (f3:FlightOperation {flight_number: 'QF815'})
    SET f3.route = 'HNL-SFO',
        f3.status = 'operated',
        f3.reason = NULL,
        f3.scheduled_time = '2026-04-15T09:00',
        f3.description = 'Honolulu to San Francisco, unaffected'

    // Alternative flight (mapped as Rebooking node type)
    MERGE (r1:Rebooking {alt_flight: 'QF109'})
    SET r1.route = 'SYD-HNL-SFO',
        r1.departure = '2026-04-14T23:40',
        r1.seats_available = 1,
        r1.cabin = 'business',
        r1.note = 'upgrade eligible as Gold member'

    // 4 bags — all auto-transferred
    MERGE (b1:Baggage {tag: 'QF77310001'})
    SET b1.destination = 'SFO',
        b1.location = 'SYD terminal',
        b1.status = 'transferred',
        b1.weight_kg = 22.3

    MERGE (b2:Baggage {tag: 'QF77310002'})
    SET b2.destination = 'SFO',
        b2.location = 'SYD terminal',
        b2.status = 'transferred',
        b2.weight_kg = 18.7

    MERGE (b3:Baggage {tag: 'QF77310003'})
    SET b3.destination = 'SFO',
        b3.location = 'SYD terminal',
        b3.status = 'transferred',
        b3.weight_kg = 15.0

    MERGE (b4:Baggage {tag: 'QF77310004'})
    SET b4.destination = 'SFO',
        b4.location = 'SYD terminal',
        b4.status = 'transferred',
        b4.weight_kg = 9.2

    // Relationships
    MERGE (c)-[:HAS_FLIGHT]->(f1)
    MERGE (c)-[:HAS_FLIGHT]->(f2)
    MERGE (c)-[:HAS_FLIGHT]->(f3)
    MERGE (c)-[:HAS_REBOOKING_OPTION]->(r1)
    MERGE (c)-[:HAS_BAGGAGE]->(b1)
    MERGE (c)-[:HAS_BAGGAGE]->(b2)
    MERGE (c)-[:HAS_BAGGAGE]->(b3)
    MERGE (c)-[:HAS_BAGGAGE]->(b4)
    MERGE (b1)-[:CHECKED_ON]->(f1)
    MERGE (b2)-[:CHECKED_ON]->(f1)
    MERGE (b3)-[:CHECKED_ON]->(f1)
    MERGE (b4)-[:CHECKED_ON]->(f1)
""")
```

### City map additions in `_query_booking_by_name_and_route_sync`

Add to the existing `city_to_code` dict:

```python
"guam": "GUM",
"honolulu": "HNL",
"san francisco": "SFO",
```

---

## 3. Tool Definitions

### Existing tools — keep, no schema change needed

`lookup_booking` and `lookup_customer` descriptions can be updated to reference the
cascading disruption scenario but the input schemas stay identical.

### New tool — `lookup_baggage`

Register in `bot.py` alongside the existing tools:

```python
# Schema
lookup_baggage_schema = FunctionSchema(
    name="lookup_baggage",
    description=(
        "Retrieve baggage status for a booking — count, tags, weight, and transfer status. "
        "Call this when the passenger asks about their bags or luggage."
    ),
    properties={
        "booking_ref": {
            "type": "string",
            "description": "The booking reference, e.g. QF-7731",
        },
    },
    required=["booking_ref"],
)
```

```python
# Handler (alongside handle_lookup_booking in bot.py)
async def handle_lookup_baggage(params: FunctionCallParams):
    booking_ref = params.arguments.get("booking_ref", "").strip()
    logger.info(f"Function call: lookup_baggage({booking_ref})")

    if not neo4j_driver:
        await params.result_callback({"error": "System unavailable."})
        return

    try:
        from knowledge_graph import query_baggage_context
        result = await query_baggage_context(neo4j_driver, booking_ref)
        if result:
            # Emit highlight events for all baggage nodes so the frontend pulses them
            if event_queue:
                for node_id in result["node_ids"]:
                    await _put_graph_event(event_queue, {"type": "highlight", "nodeId": node_id})
            await params.result_callback({"baggage": result["summary"]})
        else:
            await params.result_callback({"error": f"No baggage found for {booking_ref}."})
    except Exception as e:
        logger.error(f"lookup_baggage failed: {e}")
        await params.result_callback({"error": "Failed to retrieve baggage info."})

llm.register_function("lookup_baggage", handle_lookup_baggage)
```

### New function in `knowledge_graph.py` — `query_baggage_context`

```python
def _query_baggage_context_sync(driver, booking_ref: str) -> Optional[Dict]:
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer {booking_ref: $ref})-[:HAS_BAGGAGE]->(b:Baggage)
            RETURN collect(b) AS bags, collect(elementId(b)) AS ids
            """,
            ref=booking_ref,
        )
        record = result.single()
        if not record or not record["bags"]:
            return None

        bags = record["bags"]
        lines = [f"{len(bags)} checked bag(s):"]
        node_ids = []
        for i, b in enumerate(bags, 1):
            transferred = b.get("status") == "transferred"
            status_str = "auto-transferred to alternative flight" if transferred else b["status"]
            lines.append(
                f"  Bag {i}: tag {b['tag']}, {b['weight_kg']}kg — {status_str}"
            )
            # Construct node ID matching _query_graph_structure_sync format
            node_ids.append(f"baggage-{b['tag']}")

        return {"summary": "\n".join(lines), "node_ids": node_ids}


async def query_baggage_context(driver, booking_ref: str) -> Optional[Dict]:
    return await asyncio.to_thread(_query_baggage_context_sync, driver, booking_ref)
```

---

## 4. Frontend Graph — Stage-by-Stage Behaviour

All graph state is driven by the **existing polling event types** (`graph`, `traverse`,
`activate`, `highlight`, `context_loaded`). No new WebSocket infrastructure needed.

### Stage 1 — Identity Collected → Full Graph Loads
**Trigger:** `lookup_booking` / `lookup_customer` fires (existing behaviour)

**Events emitted:** `graph` → `traverse` × N → `activate` (customer node) → `context_loaded`

**Render:** Full node graph appears with staggered animation (existing behaviour).
The `_query_graph_structure_sync` changes needed:
- `FlightOperation` nodes with `status = CANCELLED` should set `"alert": true`
  (already works — existing code checks `status == "CANCELLED"`)
- `FlightOperation` with `status = DISRUPTED` — add `"alert": true` here too
  (currently only `CANCELLED` sets the alert badge)
- `Rebooking` node sublabel shows "23:40 tonight · Business · Gold upgrade eligible"

**Agent says after graph loads:**
> *"Von, I can see your QF107 Sydney to Guam flight has been cancelled —
> there's a hydraulic fault on the aircraft. That's also pushed your Guam to Honolulu
> connection out of reach. Let me walk you through your options."*

### Stage 2 — Options Presented
**Trigger:** keyword match in agent speech ("options", "alternative", "QF109")

**Events emitted:** `highlight` on the `Rebooking` node for QF109 (existing
`GraphHighlightObserver` handles this automatically via keyword map)

**Keyword map additions needed in `build_keyword_map`:**
```python
# Add to the existing Rebooking branch:
mapping["qf109"] = nid
mapping["tonight"] = nid
mapping["23:40"] = nid
mapping["business"] = nid
```

No new frontend code needed — the existing `highlightNode()` already pulses purple.

### Stage 3 — Baggage Query → Bag Nodes Pulse Green
**Trigger:** `lookup_baggage` tool call fires

**Events emitted by `handle_lookup_baggage`:** one `highlight` event per bag node
(4 total, emitted in sequence with no delay)

**Frontend behaviour:** existing `highlightNode()` highlights each bag node in cyan.

> For the "fan out" zoom effect described in the original plan:
> this requires new frontend code (`baggage_fan` event type + CSS animation).
> Defer to a follow-up — the highlight pulse is a working MVP.

**Agent says:**
> *"You've got four checked bags — all four have already been transferred to QF109.
> You don't need to do anything for your luggage."*

### Stage 4 — Confirmation (optional, post-MVP)
The existing system has no confirm event. Defer — the demo ends after the agent
confirms verbally. Graph state does not need to update for the initial demo.

---

## 5. Event Contract (Polling — not WebSocket)

All events go through the existing `/api/graph/poll` endpoint.
Replace the plan's WebSocket event names with the polling equivalents:

| Plan event | Actual implementation |
|---|---|
| `graph_load` | `{"type": "graph", "data": {...}}` (existing) |
| `option_focus` | `{"type": "highlight", "nodeId": "rebooking-QF109"}` (existing) |
| `baggage_lookup` | `{"type": "highlight", "nodeId": "baggage-QF77310001"}` × 4 (new, same mechanism) |
| `booking_confirmed` | deferred — no implementation yet |

---

## 6. Summary of Changes from Current Implementation

| Area | Current | Refactored |
|---|---|---|
| Passenger | Sarah Mitchell / QF-8842 | Von / QF-7731 |
| Disruption | AKL→LAX cancelled (volcanic ash) | SYD→GUM cancelled (hydraulic fault) + GUM→HNL disrupted |
| Flights | 2 legs | 3 legs (cascading) |
| Baggage | 1 bag, held | 4 bags, auto-transferred |
| Alternative | QF454 AKL-LAX economy | QF109 SYD-HNL-SFO business (Gold upgrade) |
| `lookup_baggage` tool | Not present | New tool + `query_baggage_context()` in KG |
| City map | SYD/AKL/LAX/MEL/BNE | + GUM/HNL/SFO |
| Agent name | unnamed | Aria |
| Rebooking gate | not specified | explicit — no auto-rebook |
| DISRUPTED status | not handled | add `alert: true` to DISRUPTED nodes in `_query_graph_structure_sync` |
| Baggage graph highlight | n/a | `lookup_baggage` emits 4 `highlight` events |
| Stage 4 confirmation | n/a | deferred |

### Files to change

| File | Changes |
|---|---|
| `bot.py` | `SYSTEM_INSTRUCTION_KG`, on-connect message, `lookup_baggage` handler + schema |
| `knowledge_graph.py` | `seed_graph()` data, city map, `query_baggage_context()`, DISRUPTED alert in `_query_graph_structure_sync`, keyword map additions |
