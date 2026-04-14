# Qantas Cascading Disruption Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Sarah Mitchell / QF-8842 demo scenario with Von's cascading 3-leg disruption (SYD→GUM→HNL→SFO), add a `lookup_baggage` tool that pulses all 4 bag nodes on the graph, and refine the agent's system prompt to be phased and explicitly block auto-rebooking.

**Architecture:** All changes are in two files. `knowledge_graph.py` owns data (seed, queries, graph structure, keyword map). `bot.py` owns the agent layer (system prompt, tool handlers, schemas). The frontend needs no changes — the existing `highlight`, `graph`, and `traverse` event types handle all new visual states.

**Tech Stack:** Python, Neo4j (via neo4j driver), FastAPI, pipecat LLM tool framework

---

## Context

The current demo uses Sarah Mitchell with a single AKL→LAX cancellation (volcanic ash). The new scenario has Von on a 3-leg itinerary where a maintenance fault on QF107 SYD→GUM cascades to disrupt QF821 GUM→HNL, with 4 bags auto-transferred to an alternative QF109 Business class flight. This is a stronger demo of the graph's ability to surface cascading disruption and proactive baggage handling.

## File Map

| File | Changes |
|---|---|
| `examples/vocare/knowledge_graph.py` | Seed data (Von), city map (+GUM/HNL/SFO), DISRUPTED alert, `query_baggage_context()`, keyword map additions |
| `examples/vocare/bot.py` | `SYSTEM_INSTRUCTION_KG`, on-connect message, `lookup_baggage` handler + schema + registration |

---

## Task 1: Replace seed data with Von's scenario

**Files:**
- Modify: `examples/vocare/knowledge_graph.py:14–76` (`seed_graph` function)
- Modify: `examples/vocare/knowledge_graph.py:193–199` (`city_to_code` dict in `_query_booking_by_name_and_route_sync`)

- [ ] **Step 1: Replace the seed_graph MERGE block**

In `knowledge_graph.py`, find the entire `session.run(...)` call inside `seed_graph` (lines 23–75). Replace it with:

```python
        session.run(
            """
            // Customer
            MERGE (c:Customer {booking_ref: 'QF-7731'})
            SET c.name = 'Von',
                c.phone = '+61400000000',
                c.loyalty_tier = 'Gold'

            // Leg 1 — CANCELLED (maintenance hold)
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

            // Alternative flight (Rebooking node type)
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
            """
        )
    logger.info("Neo4j graph seeded with Von / QF-7731 cascading disruption data")
```

- [ ] **Step 2: Add missing city codes to city_to_code**

In `_query_booking_by_name_and_route_sync`, find:
```python
    city_to_code = {
        "sydney": "SYD",
        "auckland": "AKL",
        "los angeles": "LAX",
        "melbourne": "MEL",
        "brisbane": "BNE",
    }
```
Replace with:
```python
    city_to_code = {
        "sydney": "SYD",
        "auckland": "AKL",
        "los angeles": "LAX",
        "melbourne": "MEL",
        "brisbane": "BNE",
        "guam": "GUM",
        "honolulu": "HNL",
        "san francisco": "SFO",
    }
```

- [ ] **Step 3: Verify syntax**

```bash
cd D:/vocare/v2/pipecat/examples/vocare
python -c "import ast; ast.parse(open('knowledge_graph.py').read()); print('Syntax OK')"
```
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/knowledge_graph.py
git commit -m "feat: replace demo seed data with Von QF-7731 cascading disruption scenario"
```

---

## Task 2: Fix DISRUPTED alert + add QF109 keyword map entries

**Files:**
- Modify: `examples/vocare/knowledge_graph.py:337–355` (`_query_graph_structure_sync` flight node builder)
- Modify: `examples/vocare/knowledge_graph.py:553–566` (`build_keyword_map` Rebooking branch)

- [ ] **Step 1: Add DISRUPTED to the alert condition in _query_graph_structure_sync**

Find the flight node builder inside `_query_graph_structure_sync`:
```python
            nodes.append(
                {
                    "id": fid,
                    "type": "FlightOperation",
                    "label": f"{f['flight_number']} \u00b7 {route}",
                    "sublabel": status_text,
                    "alert": status == "CANCELLED",
                }
            )
```
Replace with:
```python
            nodes.append(
                {
                    "id": fid,
                    "type": "FlightOperation",
                    "label": f"{f['flight_number']} \u00b7 {route}",
                    "sublabel": status_text,
                    "alert": status in ("CANCELLED", "DISRUPTED"),
                }
            )
```

- [ ] **Step 2: Add DISRUPTED to the status_text builder**

Find the status_text logic just above:
```python
            if status == "CANCELLED":
                status_text = f"Cancelled \u2014 {f.get('reason', 'unknown')}"
            elif status == "OPERATED":
                status_text = "Arrived on time"
            else:
                status_text = status
```
Replace with:
```python
            if status == "CANCELLED":
                status_text = f"Cancelled \u2014 {f.get('reason', 'unknown')}"
            elif status == "DISRUPTED":
                status_text = f"Disrupted \u2014 {f.get('reason', 'missed connection')}"
            elif status == "OPERATED":
                status_text = "Arrived on time"
            else:
                status_text = status
```

- [ ] **Step 3: Add QF109 keyword map entries in build_keyword_map**

In `build_keyword_map`, find the Rebooking branch:
```python
        elif ntype == "Rebooking":
            # Match on alt flight number and "rebook" keywords
            label = node.get("label", "")
            flight_num = label.split("\u00b7")[0].strip() if "\u00b7" in label else label
            if flight_num:
                mapping[flight_num.lower()] = nid
            # General rebooking keywords map to first rebooking node
            if "rebook" not in mapping:
                mapping["rebook"] = nid
                mapping["rebooking"] = nid
                mapping["rebooked"] = nid
                mapping["alternative"] = nid
                mapping["options"] = nid
                mapping["next flight"] = nid
```
Replace with:
```python
        elif ntype == "Rebooking":
            # Match on alt flight number and "rebook" keywords
            label = node.get("label", "")
            flight_num = label.split("\u00b7")[0].strip() if "\u00b7" in label else label
            if flight_num:
                mapping[flight_num.lower()] = nid
            # General rebooking keywords map to first rebooking node
            if "rebook" not in mapping:
                mapping["rebook"] = nid
                mapping["rebooking"] = nid
                mapping["rebooked"] = nid
                mapping["alternative"] = nid
                mapping["options"] = nid
                mapping["next flight"] = nid
                mapping["tonight"] = nid
                mapping["23:40"] = nid
                mapping["business"] = nid
                mapping["upgrade"] = nid
                mapping["qf109"] = nid
```

- [ ] **Step 4: Verify syntax**

```bash
cd D:/vocare/v2/pipecat/examples/vocare
python -c "import ast; ast.parse(open('knowledge_graph.py').read()); print('Syntax OK')"
```
Expected: `Syntax OK`

- [ ] **Step 5: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/knowledge_graph.py
git commit -m "feat: add DISRUPTED alert badge and QF109 keyword map entries"
```

---

## Task 3: Add query_baggage_context to knowledge_graph.py

**Files:**
- Modify: `examples/vocare/knowledge_graph.py` — add new functions after `build_keyword_map` (end of file)

- [ ] **Step 1: Append query_baggage_context at end of knowledge_graph.py**

Add these two functions at the very end of `knowledge_graph.py` (after `build_keyword_map`):

```python

def _query_baggage_context_sync(driver, booking_ref: str) -> Optional[Dict]:
    """Query baggage for a booking — returns summary text and graph node IDs.

    Args:
        driver: Neo4j driver instance.
        booking_ref: Customer booking reference.

    Returns:
        Dict with "summary" (str for LLM) and "node_ids" (list for frontend highlights),
        or None if no baggage found.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer {booking_ref: $ref})-[:HAS_BAGGAGE]->(b:Baggage)
            RETURN collect(b) AS bags
            """,
            ref=booking_ref,
        )
        record = result.single()
        if not record or not record["bags"]:
            return None

        bags = record["bags"]
        count = len(bags)
        lines = [f"{count} checked bag{'s' if count != 1 else ''}:"]
        node_ids = []
        for i, b in enumerate(bags, 1):
            status = b.get("status", "unknown")
            status_str = (
                "auto-transferred to alternative flight"
                if status == "transferred"
                else status
            )
            lines.append(
                f"  Bag {i}: tag {b['tag']}, {b.get('weight_kg', '?')}kg — {status_str}"
            )
            node_ids.append(f"baggage-{b['tag']}")

        return {"summary": "\n".join(lines), "node_ids": node_ids}


async def query_baggage_context(driver, booking_ref: str) -> Optional[Dict]:
    """Query baggage for a booking, async-safe.

    Args:
        driver: Neo4j driver instance.
        booking_ref: Customer booking reference.

    Returns:
        Dict with "summary" and "node_ids", or None if not found.
    """
    return await asyncio.to_thread(_query_baggage_context_sync, driver, booking_ref)
```

- [ ] **Step 2: Verify syntax**

```bash
cd D:/vocare/v2/pipecat/examples/vocare
python -c "import ast; ast.parse(open('knowledge_graph.py').read()); print('Syntax OK')"
```
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/knowledge_graph.py
git commit -m "feat: add query_baggage_context for lookup_baggage tool"
```

---

## Task 4: Add lookup_baggage tool to bot.py

**Files:**
- Modify: `examples/vocare/bot.py:540–622` (tool handler + schema + registration block inside `run_bot`)

- [ ] **Step 1: Add handle_lookup_baggage handler**

Inside `run_bot`, find `handle_lookup_customer` function. Add `handle_lookup_baggage` immediately after it (before the `# Register tools on the LLM` comment):

```python
    async def handle_lookup_baggage(params: FunctionCallParams):
        """Retrieve baggage status for a booking and highlight bag nodes on the graph."""
        booking_ref = params.arguments.get("booking_ref", "").strip()
        logger.info(f"Function call: lookup_baggage({booking_ref})")

        if not neo4j_driver:
            await params.result_callback({"error": "System unavailable, please try again later."})
            return

        try:
            from knowledge_graph import query_baggage_context

            result = await query_baggage_context(neo4j_driver, booking_ref)
            if result:
                # Highlight each bag node on the frontend graph
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
            await params.result_callback({"error": "Failed to retrieve baggage info. Please try again."})
```

- [ ] **Step 2: Add lookup_baggage_schema and register the function**

Find the existing tool schema block:
```python
        lookup_booking_schema = FunctionSchema(
```
Add the baggage schema immediately before it:
```python
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
                    "description": "The booking reference, e.g. QF-7731",
                },
            },
            required=["booking_ref"],
        )
```

- [ ] **Step 3: Register the function and add to ToolsSchema**

Find:
```python
        llm.register_function("lookup_booking", handle_lookup_booking)
        llm.register_function("lookup_customer", handle_lookup_customer)
```
Replace with:
```python
        llm.register_function("lookup_booking", handle_lookup_booking)
        llm.register_function("lookup_customer", handle_lookup_customer)
        llm.register_function("lookup_baggage", handle_lookup_baggage)
```

Find:
```python
        tools = ToolsSchema(
            standard_tools=[lookup_booking_schema, lookup_customer_schema]
        )
```
Replace with:
```python
        tools = ToolsSchema(
            standard_tools=[lookup_booking_schema, lookup_customer_schema, lookup_baggage_schema]
        )
```

- [ ] **Step 4: Verify syntax**

```bash
cd D:/vocare/v2/pipecat/examples/vocare
python -c "import ast; ast.parse(open('bot.py').read()); print('Syntax OK')"
```
Expected: `Syntax OK`

- [ ] **Step 5: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/bot.py
git commit -m "feat: add lookup_baggage tool with graph node highlighting"
```

---

## Task 5: Update system instruction and agent name

**Files:**
- Modify: `examples/vocare/bot.py:156–170` (`SYSTEM_INSTRUCTION_KG`)
- Modify: `examples/vocare/bot.py:656–669` (on-connect system message injection)

- [ ] **Step 1: Replace SYSTEM_INSTRUCTION_KG**

Find:
```python
SYSTEM_INSTRUCTION_KG = (
    "You are a Qantas customer service agent in a voice call. "
    ...
)
```
Replace with:
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
    "Explain the cause in ONE sentence only. "
    "Then immediately surface the downstream impact: if a connecting flight is also disrupted, "
    "name that leg specifically. Do not over-explain. "

    # --- Phase 4: Options (DO NOT REBOOK) ---
    "Do NOT confirm any rebooking automatically. "
    "Present 2 to 3 concrete options clearly. Each option should include the new flight time, "
    "routing, and any upgrade or compensation attached. "
    "Ask the passenger which option they prefer before taking any action. "

    # --- Phase 5: Baggage Handling ---
    "If the passenger asks about their baggage, call the lookup_baggage tool immediately. "
    "Confirm the exact number of checked bags and whether they have been automatically "
    "transferred to the alternative flight. Be specific about the bag count. "

    # --- Tone ---
    "Always be human, concise, and proactive. Never list more than 3 items in one breath. "
    "Do not use filler phrases like 'Certainly!' or 'Of course!'. "
)
```

- [ ] **Step 2: Update on-connect injection message**

Find the KG branch of `on_client_connected`:
```python
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
```
Replace with:
```python
        if use_kg:
            context.add_message(
                {
                    "role": "system",
                    "content": (
                        "Greet the caller warmly as Aria, a Qantas service agent. "
                        "Ask for their booking reference number. "
                        "If they don't have it, let them know you can look them up "
                        "by name and flight route."
                    ),
                }
            )
```

- [ ] **Step 3: Verify syntax**

```bash
cd D:/vocare/v2/pipecat/examples/vocare
python -c "import ast; ast.parse(open('bot.py').read()); print('Syntax OK')"
```
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/bot.py
git commit -m "feat: update system prompt to phased Aria persona, block auto-rebooking"
```

---

## Verification — End-to-End Smoke Test

After all tasks are complete:

1. Wipe and re-seed Neo4j (restart the bot with `NEO4J_SEED=true`):
   ```bash
   cd D:/vocare/v2/pipecat/examples/vocare
   NEO4J_SEED=true python bot.py
   ```

2. Open http://localhost:7860, enable Knowledge Graph, click Connect.

3. Say **"My booking reference is QF-7731"** — verify:
   - Graph loads with 3 flight nodes: QF107 (red alert), QF821 (red/amber alert), QF815 (normal)
   - Rebooking node QF109 appears in purple
   - 4 Baggage nodes appear in green
   - Agent introduces as "Aria" and explains the cascading disruption

4. Say **"What about my bags?"** — verify:
   - All 4 bag nodes pulse cyan (highlight events fired)
   - Agent confirms "four checked bags, all transferred to QF109"

5. Say **"What are my options?"** — verify:
   - QF109 Rebooking node highlights (keyword match: "options")
   - Agent presents options without auto-confirming any rebooking

6. Say **"I'm Von, Sydney to San Francisco"** (lookup by name+route) — verify:
   - `lookup_customer` finds QF-7731 correctly (city map covers SYD + SFO)
