# Qantas Context Graph Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the static Qantas knowledge graph into a demonstrable *context graph* by adding three layers — temporal event chain, pre-assembled CallContext node, and provenance labels on edges — alongside replacing the seed data with Von's cascading 3-leg disruption scenario and a new `lookup_baggage` tool.

**Architecture:** All changes are in `knowledge_graph.py` (data + queries), `bot.py` (tools + prompt), and `static/index.html` (new `Event` node type in the renderer). Three additive Neo4j layers on top of the existing schema: (1) `:Event` nodes chained by `:TRIGGERED` edges for temporality, (2) a `:CallContext` node pre-computing the agent brief for call-readiness, (3) `source` properties on edges for provenance. The existing `Customer`, `FlightOperation`, `Baggage`, `Rebooking`, `Communication` node types are untouched. The existing polling + `handleGraphEvent` pipeline handles all new visual states.

**Tech Stack:** Python, Neo4j (neo4j driver), FastAPI, pipecat LLM tool framework, vanilla JS canvas graph renderer

---

## Context

Current demo: Sarah Mitchell / QF-8842, single AKL→LAX cancellation (volcanic ash). The graph shows *state* — it answers "what records exist?" not "what happened and why?". This is a knowledge graph, not a context graph. To prove the thesis we need three things the current graph lacks: temporal sequence (Event chain with TRIGGERED edges showing the cascade), call-readiness (CallContext node pre-assembled before the phone rings), and provenance (source labels showing which system each edge came from). These are the three things that turn "we use Neo4j" into "we built a context graph".

New scenario: Von / QF-7731, SYD→GUM→HNL→SFO, QF107 cancelled (hydraulic fault) cascading to QF821 disruption, 4 bags auto-transferred, alternative QF109 Business class tonight.

---

## File Map

| File | Changes |
|---|---|
| `examples/vocare/knowledge_graph.py` | `seed_graph()` — full Von scenario + Event chain + CallContext + source edges; `_query_graph_structure_sync()` — include Event nodes + source on edges; `_query_customer_context_sync()` — read CallContext first; `build_traversal_sequence()` — add TRIGGERED traversal; `build_keyword_map()` — DISRUPTED status + QF109 keywords; `_query_graph_structure_sync()` — DISRUPTED alert; city_to_code + GUM/HNL/SFO; new `query_baggage_context()` |
| `examples/vocare/bot.py` | `SYSTEM_INSTRUCTION_KG`, on-connect message, `lookup_baggage` handler + schema + registration |
| `examples/vocare/static/index.html` | Add `Event` to `TYPE_COLORS` and `NODE_ICONS` |

---

## Task 1: Replace seed data — Von scenario + Event chain + CallContext + provenance edges

**Files:**
- Modify: `examples/vocare/knowledge_graph.py:14–76` (`seed_graph`)
- Modify: `examples/vocare/knowledge_graph.py:193–199` (`city_to_code` in `_query_booking_by_name_and_route_sync`)

- [ ] **Step 1: Replace the entire session.run() block inside seed_graph**

Find the `session.run(...)` call (lines 23–75). Replace the entire contents (keep the outer `with driver.session() as session:` wrapper) with:

```python
        session.run(
            """
            // ── Customer ──────────────────────────────────────────────────
            MERGE (c:Customer {booking_ref: 'QF-7731'})
            SET c.name = 'Von',
                c.phone = '+61400000000',
                c.loyalty_tier = 'Gold'

            // ── Flights ───────────────────────────────────────────────────
            MERGE (f1:FlightOperation {flight_number: 'QF107'})
            SET f1.route = 'SYD-GUM',
                f1.status = 'CANCELLED',
                f1.reason = 'hydraulic fault on VH-OQF',
                f1.scheduled_time = '2026-04-14T08:30',
                f1.description = 'Sydney to Guam, cancelled due to maintenance hold'

            MERGE (f2:FlightOperation {flight_number: 'QF821'})
            SET f2.route = 'GUM-HNL',
                f2.status = 'DISRUPTED',
                f2.reason = 'missed connection due to QF107 cancellation',
                f2.scheduled_time = '2026-04-14T14:15',
                f2.description = 'Guam to Honolulu, disrupted by upstream cancellation'

            MERGE (f3:FlightOperation {flight_number: 'QF815'})
            SET f3.route = 'HNL-SFO',
                f3.status = 'operated',
                f3.reason = NULL,
                f3.scheduled_time = '2026-04-15T09:00',
                f3.description = 'Honolulu to San Francisco, unaffected'

            // ── Alternative flight (Rebooking node type) ──────────────────
            MERGE (r1:Rebooking {alt_flight: 'QF109'})
            SET r1.route = 'SYD-HNL-SFO',
                r1.departure = '2026-04-14T23:40',
                r1.seats_available = 1,
                r1.cabin = 'business',
                r1.note = 'upgrade eligible as Gold member'

            // ── Baggage (4 bags, all auto-transferred) ────────────────────
            MERGE (b1:Baggage {tag: 'QF77310001'})
            SET b1.destination = 'SFO', b1.location = 'SYD terminal',
                b1.status = 'transferred', b1.weight_kg = 22.3

            MERGE (b2:Baggage {tag: 'QF77310002'})
            SET b2.destination = 'SFO', b2.location = 'SYD terminal',
                b2.status = 'transferred', b2.weight_kg = 18.7

            MERGE (b3:Baggage {tag: 'QF77310003'})
            SET b3.destination = 'SFO', b3.location = 'SYD terminal',
                b3.status = 'transferred', b3.weight_kg = 15.0

            MERGE (b4:Baggage {tag: 'QF77310004'})
            SET b4.destination = 'SFO', b4.location = 'SYD terminal',
                b4.status = 'transferred', b4.weight_kg = 9.2

            // ── LAYER 1: Event chain (temporal provenance) ─────────────────
            MERGE (e1:Event {id: 'evt-001'})
            SET e1.type = 'FLIGHT_CANCELLED',
                e1.timestamp = '2026-04-14T06:15',
                e1.description = 'QF107 grounded — hydraulic fault VH-OQF'

            MERGE (e2:Event {id: 'evt-002'})
            SET e2.type = 'CONNECTION_BROKEN',
                e2.timestamp = '2026-04-14T06:17',
                e2.description = 'QF821 GUM→HNL missed — downstream of QF107'

            MERGE (e3:Event {id: 'evt-003'})
            SET e3.type = 'BAGS_AUTO_TRANSFERRED',
                e3.timestamp = '2026-04-14T06:45',
                e3.description = '4 bags rerouted to QF109 SYD→HNL→SFO'

            MERGE (e1)-[:TRIGGERED]->(e2)
            MERGE (e2)-[:TRIGGERED]->(e3)
            MERGE (c)-[:EXPERIENCED]->(e1)

            // ── LAYER 2: CallContext node (call-readiness brief) ───────────
            MERGE (ctx:CallContext {booking_ref: 'QF-7731'})
            SET ctx.primary_issue = 'QF107 cancellation cascades to QF821 disruption',
                ctx.recommended_action = 'Offer QF109 SYD→HNL→SFO Business, 23:40 tonight',
                ctx.loyalty_flag = 'Gold — upgrade eligible',
                ctx.baggage_status = '4 bags auto-transferred to QF109, no action needed',
                ctx.urgency = 'HIGH'

            MERGE (c)-[:HAS_CALL_CONTEXT]->(ctx)

            // ── Core relationships (with LAYER 3: provenance source) ───────
            MERGE (c)-[:HAS_FLIGHT {source: 'Qantas OpsDB', fetched_at: '2026-04-14T06:00'}]->(f1)
            MERGE (c)-[:HAS_FLIGHT {source: 'Qantas OpsDB', fetched_at: '2026-04-14T06:00'}]->(f2)
            MERGE (c)-[:HAS_FLIGHT {source: 'Qantas OpsDB', fetched_at: '2026-04-14T06:00'}]->(f3)
            MERGE (c)-[:HAS_REBOOKING_OPTION {source: 'Inventory API', fetched_at: '2026-04-14T06:50'}]->(r1)
            MERGE (c)-[:HAS_BAGGAGE {source: 'Baggage Handling System', fetched_at: '2026-04-14T06:45'}]->(b1)
            MERGE (c)-[:HAS_BAGGAGE {source: 'Baggage Handling System', fetched_at: '2026-04-14T06:45'}]->(b2)
            MERGE (c)-[:HAS_BAGGAGE {source: 'Baggage Handling System', fetched_at: '2026-04-14T06:45'}]->(b3)
            MERGE (c)-[:HAS_BAGGAGE {source: 'Baggage Handling System', fetched_at: '2026-04-14T06:45'}]->(b4)
            MERGE (b1)-[:CHECKED_ON]->(f1)
            MERGE (b2)-[:CHECKED_ON]->(f1)
            MERGE (b3)-[:CHECKED_ON]->(f1)
            MERGE (b4)-[:CHECKED_ON]->(f1)
            """
        )
    logger.info("Neo4j graph seeded with Von / QF-7731 context graph (temporal + call-readiness + provenance)")
```

- [ ] **Step 2: Add missing city codes**

Find `city_to_code` dict in `_query_booking_by_name_and_route_sync`:
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
git commit -m "feat: seed Von QF-7731 context graph — event chain, call context, provenance edges"
```

---

## Task 2: Update _query_graph_structure_sync — Event nodes, source labels, DISRUPTED alert

**Files:**
- Modify: `examples/vocare/knowledge_graph.py:263–416` (`_query_graph_structure_sync`)

- [ ] **Step 1: Expand the Cypher query to fetch Event nodes and source on edges**

Find the `session.run(...)` call inside `_query_graph_structure_sync` (lines 274–291). Replace it with:

```python
        result = session.run(
            """
            MATCH (c:Customer {booking_ref: $ref})
            OPTIONAL MATCH (c)-[hf:HAS_FLIGHT]->(f:FlightOperation)
            OPTIONAL MATCH (c)-[hb:HAS_BAGGAGE]->(b:Baggage)
            OPTIONAL MATCH (c)-[hr:HAS_REBOOKING_OPTION]->(r:Rebooking)
            OPTIONAL MATCH (c)-[:RECEIVED_COMM]->(comm:Communication)
            OPTIONAL MATCH (b)-[co:CHECKED_ON]->(bf:FlightOperation)
            OPTIONAL MATCH (c)-[:EXPERIENCED]->(e1:Event)
            OPTIONAL MATCH (e1)-[:TRIGGERED*0..5]->(echain:Event)
            RETURN c,
                   collect(DISTINCT {flight: f, source: hf.source}) AS flights,
                   collect(DISTINCT {bag: b, source: hb.source}) AS baggage,
                   collect(DISTINCT {rebooking: r, source: hr.source}) AS rebookings,
                   collect(DISTINCT comm) AS comms,
                   collect(DISTINCT {bag_tag: b.tag, flight_num: bf.flight_number}) AS bag_flights,
                   collect(DISTINCT echain) AS events
            """,
            ref=booking_ref,
        )
```

- [ ] **Step 2: Update the record unpacking and node/edge builders**

Find the block that starts with `record = result.single()` and builds nodes/edges. Replace it entirely with:

```python
        record = result.single()
        if not record or record["c"] is None:
            return None

        customer = record["c"]
        nodes: List[Dict] = []
        edges: List[Dict] = []

        city_names = {
            "SYD": "Sydney", "AKL": "Auckland", "LAX": "Los Angeles",
            "MEL": "Melbourne", "BNE": "Brisbane",
            "GUM": "Guam", "HNL": "Honolulu", "SFO": "San Francisco",
        }

        def friendly_route(route: str) -> str:
            parts = route.split("-")
            return " to ".join(city_names.get(p, p) for p in parts)

        def friendly_time(iso: str) -> str:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(iso)
                try:
                    return dt.strftime("%b %#d, %#I:%M %p")
                except ValueError:
                    return dt.strftime("%b %-d, %-I:%M %p")
            except Exception:
                return iso

        cust_id = f"customer-{customer['booking_ref']}"
        nodes.append({
            "id": cust_id,
            "type": "Customer",
            "label": customer["name"],
            "sublabel": f"Booking {customer['booking_ref']}  \u00b7  {customer['loyalty_tier']} member",
        })

        # Flight nodes
        for item in record["flights"]:
            f = item["flight"]
            if f is None:
                continue
            source = item.get("source") or "Qantas OpsDB"
            fid = f"flight-{f['flight_number']}"
            status = f["status"].upper()
            route = friendly_route(f["route"])
            if status == "CANCELLED":
                status_text = f"Cancelled \u2014 {f.get('reason', 'unknown')}"
            elif status == "DISRUPTED":
                status_text = f"Disrupted \u2014 {f.get('reason', 'missed connection')}"
            elif status == "OPERATED":
                status_text = "Arrived on time"
            else:
                status_text = status
            nodes.append({
                "id": fid,
                "type": "FlightOperation",
                "label": f"{f['flight_number']} \u00b7 {route}",
                "sublabel": status_text,
                "alert": status in ("CANCELLED", "DISRUPTED"),
            })
            edges.append({
                "source": cust_id,
                "target": fid,
                "label": source,
            })

        # Baggage nodes
        bag_items = [item for item in record["baggage"] if item.get("bag") is not None]
        bag_count = len(bag_items)
        for i, item in enumerate(bag_items, 1):
            b = item["bag"]
            source = item.get("source") or "Baggage Handling System"
            bid = f"baggage-{b['tag']}"
            location = b["location"]
            status = "Auto-transferred" if b["status"] == "transferred" else b["status"]
            bag_label = "Checked Baggage" if bag_count == 1 else f"Bag {i}"
            nodes.append({
                "id": bid,
                "type": "Baggage",
                "label": bag_label,
                "sublabel": f"{location} \u00b7 {status}",
            })
            edges.append({
                "source": cust_id,
                "target": bid,
                "label": source,
            })

        # Rebooking nodes
        for item in record["rebookings"]:
            r = item["rebooking"]
            if r is None:
                continue
            source = item.get("source") or "Inventory API"
            rid = f"rebooking-{r['alt_flight']}"
            route = friendly_route(r["route"])
            time = friendly_time(r["departure"])
            seats = r["seats_available"]
            seat_word = "seat" if seats == 1 else "seats"
            note = f" ({r['note']})" if r.get("note") else ""
            nodes.append({
                "id": rid,
                "type": "Rebooking",
                "label": f"{r['alt_flight']} \u00b7 {route}",
                "sublabel": f"{time} \u00b7 {seats} {seat_word}{note}",
            })
            edges.append({
                "source": cust_id,
                "target": rid,
                "label": source,
            })

        # Communication nodes
        for comm in record["comms"]:
            cid = f"comm-{comm['channel']}-{comm['sent_at']}"
            channel = comm["channel"]
            time = friendly_time(comm["sent_at"])
            nodes.append({
                "id": cid,
                "type": "Communication",
                "label": f"Sent via {channel}",
                "sublabel": time,
            })
            edges.append({"source": cust_id, "target": cid, "label": "Notified"})

        # Baggage → FlightOperation edges
        for link in record["bag_flights"]:
            if link["bag_tag"] and link["flight_num"]:
                edges.append({
                    "source": f"baggage-{link['bag_tag']}",
                    "target": f"flight-{link['flight_num']}",
                    "label": "Checked on",
                })

        # Event chain nodes (temporal layer)
        seen_events = set()
        prev_event_id = None
        for e in record["events"]:
            if e is None or e["id"] in seen_events:
                continue
            seen_events.add(e["id"])
            eid = f"event-{e['id']}"
            nodes.append({
                "id": eid,
                "type": "Event",
                "label": e["type"].replace("_", " ").title(),
                "sublabel": e.get("description", ""),
            })
            if prev_event_id is None:
                # First event: link from customer
                edges.append({"source": cust_id, "target": eid, "label": "Experienced"})
            else:
                edges.append({"source": prev_event_id, "target": eid, "label": "Triggered"})
            prev_event_id = eid

        return {"nodes": nodes, "edges": edges}
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
git commit -m "feat: include Event chain and source labels in graph structure query"
```

---

## Task 3: Update _query_customer_context_sync to read CallContext first

**Files:**
- Modify: `examples/vocare/knowledge_graph.py:79–163` (`_query_customer_context_sync`)

- [ ] **Step 1: Add CallContext to the Cypher query**

Find the `session.run(...)` inside `_query_customer_context_sync`. Replace it with:

```python
        result = session.run(
            """
            MATCH (c:Customer {booking_ref: $ref})
            OPTIONAL MATCH (c)-[:HAS_FLIGHT]->(f:FlightOperation)
            OPTIONAL MATCH (c)-[:HAS_BAGGAGE]->(b:Baggage)
            OPTIONAL MATCH (c)-[:HAS_REBOOKING_OPTION]->(r:Rebooking)
            OPTIONAL MATCH (c)-[:RECEIVED_COMM]->(comm:Communication)
            OPTIONAL MATCH (c)-[:HAS_CALL_CONTEXT]->(ctx:CallContext)
            RETURN c,
                   collect(DISTINCT f) AS flights,
                   collect(DISTINCT b) AS baggage,
                   collect(DISTINCT r) AS rebooking_options,
                   collect(DISTINCT comm) AS communications,
                   ctx
            """,
            ref=booking_ref,
        )
```

- [ ] **Step 2: Add CallContext brief at the top of the formatted output**

Find the block that builds `lines = []` and appends the customer summary. Add the CallContext section immediately after `lines.append("")` (after the initial header):

```python
        # CallContext pre-assembled brief (call-readiness layer)
        ctx = record.get("ctx")
        if ctx:
            lines.append("=== PRE-CALL BRIEF (Context Graph) ===")
            lines.append("")
            lines.append(f"Primary issue:       {ctx['primary_issue']}")
            lines.append(f"Recommended action:  {ctx['recommended_action']}")
            lines.append(f"Loyalty flag:        {ctx['loyalty_flag']}")
            lines.append(f"Baggage status:      {ctx['baggage_status']}")
            lines.append(f"Urgency:             {ctx['urgency']}")
            lines.append("")
```

Place this block before the existing `lines.append(f"Customer: ...")` line.

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
git commit -m "feat: prepend CallContext brief to LLM context — call-readiness layer"
```

---

## Task 4: Update build_traversal_sequence and build_keyword_map

**Files:**
- Modify: `examples/vocare/knowledge_graph.py:432–485` (`build_traversal_sequence`)
- Modify: `examples/vocare/knowledge_graph.py:488–586` (`build_keyword_map`)

- [ ] **Step 1: Add Event traversal order to build_traversal_sequence**

Find:
```python
    traversal_order = [
        "Booked flight",
        "Checked bag",
        "Rebooking option",
        "Notified",
        "Checked on",
    ]
```
Replace with:
```python
    traversal_order = [
        "Booked flight",
        "Checked bag",
        "Rebooking option",
        "Notified",
        "Checked on",
        "Experienced",
        "Triggered",
    ]
```

Note: the edge labels from Task 2 use source system names (e.g. "Qantas OpsDB") not "Booked flight" for flight edges. The traversal_order here must match the actual edge labels emitted by `_query_graph_structure_sync`. Cross-check: flight edges now use `source` as label (e.g. "Qantas OpsDB"), baggage edges use "Baggage Handling System", rebooking uses "Inventory API". Only "Checked on", "Notified", "Experienced", "Triggered" use string labels.

Update the full traversal_order to match:
```python
    traversal_order = [
        "Qantas OpsDB",
        "Baggage Handling System",
        "Inventory API",
        "Notified",
        "Checked on",
        "Experienced",
        "Triggered",
    ]
```

- [ ] **Step 2: Add QF109 and event keywords to build_keyword_map**

In `build_keyword_map`, find the Rebooking branch and add new keywords. Find:
```python
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

Also add an Event branch at the end of the `for node in graph["nodes"]:` loop (after the `Communication` branch):
```python
        elif ntype == "Event":
            # Match on event type keywords
            etype = node.get("label", "").lower()
            if "cancelled" in etype or "cancellation" in etype:
                mapping["grounded"] = nid
                mapping["fault"] = nid
                mapping["hydraulic"] = nid
            elif "connection" in etype or "missed" in etype:
                mapping["missed"] = nid
                mapping["connection broken"] = nid
            elif "bag" in etype or "transfer" in etype:
                mapping["rerouted"] = nid
                mapping["transferred"] = nid
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
git commit -m "feat: update traversal sequence for source labels and Event keyword map"
```

---

## Task 5: Add query_baggage_context to knowledge_graph.py

**Files:**
- Modify: `examples/vocare/knowledge_graph.py` — append after `build_keyword_map`

- [ ] **Step 1: Append at end of knowledge_graph.py**

```python

def _query_baggage_context_sync(driver, booking_ref: str) -> Optional[Dict]:
    """Query baggage for a booking — returns LLM summary and graph node IDs for highlighting.

    Args:
        driver: Neo4j driver instance.
        booking_ref: Customer booking reference.

    Returns:
        Dict with "summary" (str) and "node_ids" (list[str]), or None if no baggage found.
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

## Task 6: Add Event node type to frontend renderer

**Files:**
- Modify: `examples/vocare/static/index.html:849–864` (`TYPE_COLORS` and `NODE_ICONS`)

- [ ] **Step 1: Add Event to TYPE_COLORS**

Find:
```javascript
    const TYPE_COLORS = {
      Customer:        { hex: '#f59e0b', rgb: '245,158,11' },
      FlightOperation: { hex: '#3b82f6', rgb: '59,130,246' },
      Baggage:         { hex: '#10b981', rgb: '16,185,129' },
      Rebooking:       { hex: '#8b5cf6', rgb: '139,92,246' },
      Communication:   { hex: '#f97316', rgb: '249,115,22' },
    };
```
Replace with:
```javascript
    const TYPE_COLORS = {
      Customer:        { hex: '#f59e0b', rgb: '245,158,11' },
      FlightOperation: { hex: '#3b82f6', rgb: '59,130,246' },
      Baggage:         { hex: '#10b981', rgb: '16,185,129' },
      Rebooking:       { hex: '#8b5cf6', rgb: '139,92,246' },
      Communication:   { hex: '#f97316', rgb: '249,115,22' },
      Event:           { hex: '#6366f1', rgb: '99,102,241' },
    };
```

- [ ] **Step 2: Add Event to NODE_ICONS**

Find:
```javascript
    const NODE_ICONS = {
      Customer: '\u{1F464}',
      FlightOperation: '\u2708\uFE0F',
      Baggage: '\u{1F9F3}',
      Rebooking: '\u{1F504}',
      Communication: '\u2709\uFE0F',
    };
```
Replace with:
```javascript
    const NODE_ICONS = {
      Customer: '\u{1F464}',
      FlightOperation: '\u2708\uFE0F',
      Baggage: '\u{1F9F3}',
      Rebooking: '\u{1F504}',
      Communication: '\u2709\uFE0F',
      Event: '\u26A1',
    };
```

- [ ] **Step 3: Add Event to graph legend**

Find:
```html
      <div class="graph-legend" id="graphLegend" style="display:none;">
        <div class="legend-item"><div class="legend-dot" style="background:#f59e0b;"></div>Customer</div>
        <div class="legend-item"><div class="legend-dot" style="background:#3b82f6;"></div>Flight</div>
        <div class="legend-item"><div class="legend-dot" style="background:#10b981;"></div>Baggage</div>
        <div class="legend-item"><div class="legend-dot" style="background:#8b5cf6;"></div>Rebooking</div>
        <div class="legend-item"><div class="legend-dot" style="background:#f97316;"></div>Comms</div>
      </div>
```
Replace with:
```html
      <div class="graph-legend" id="graphLegend" style="display:none;">
        <div class="legend-item"><div class="legend-dot" style="background:#f59e0b;"></div>Customer</div>
        <div class="legend-item"><div class="legend-dot" style="background:#3b82f6;"></div>Flight</div>
        <div class="legend-item"><div class="legend-dot" style="background:#10b981;"></div>Baggage</div>
        <div class="legend-item"><div class="legend-dot" style="background:#8b5cf6;"></div>Rebooking</div>
        <div class="legend-item"><div class="legend-dot" style="background:#f97316;"></div>Comms</div>
        <div class="legend-item"><div class="legend-dot" style="background:#6366f1;"></div>Event</div>
      </div>
```

- [ ] **Step 4: Verify HTML parses**

```bash
cd D:/vocare/v2/pipecat/examples/vocare
python -c "
from html.parser import HTMLParser
class V(HTMLParser): pass
V().feed(open('static/index.html').read())
print('HTML parse OK')
"
```
Expected: `HTML parse OK`

- [ ] **Step 5: Commit**

```bash
cd D:/vocare/v2/pipecat
git add examples/vocare/static/index.html
git commit -m "feat: add Event node type (indigo) to graph renderer and legend"
```

---

## Task 7: Add lookup_baggage tool to bot.py

**Files:**
- Modify: `examples/vocare/bot.py` — inside `run_bot`, tool handlers + schema + registration

- [ ] **Step 1: Add handle_lookup_baggage handler inside run_bot**

Find `handle_lookup_customer` function. Add `handle_lookup_baggage` immediately after it (before `# Register tools on the LLM`):

```python
    async def handle_lookup_baggage(params: FunctionCallParams):
        """Retrieve baggage status and highlight all bag nodes on the frontend graph."""
        booking_ref = params.arguments.get("booking_ref", "").strip()
        logger.info(f"Function call: lookup_baggage({booking_ref})")

        if not neo4j_driver:
            await params.result_callback({"error": "System unavailable, please try again later."})
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
            await params.result_callback({"error": "Failed to retrieve baggage info. Please try again."})
```

- [ ] **Step 2: Add lookup_baggage_schema**

Find `lookup_booking_schema = FunctionSchema(`. Add baggage schema immediately before it:

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

- [ ] **Step 3: Register function and add to ToolsSchema**

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

## Task 8: Update system instruction and agent name

**Files:**
- Modify: `examples/vocare/bot.py:156–170` (`SYSTEM_INSTRUCTION_KG`)
- Modify: `examples/vocare/bot.py` (on-connect message inside `on_client_connected`)

- [ ] **Step 1: Replace SYSTEM_INSTRUCTION_KG**

Find the full `SYSTEM_INSTRUCTION_KG = (...)` block. Replace it with:

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
    "After retrieving their situation, the PRE-CALL BRIEF section tells you exactly what happened. "
    "Acknowledge the disruption briefly and empathetically — explain the cause in ONE sentence. "
    "Then immediately surface the downstream impact: if a connecting flight is also disrupted, "
    "name that leg specifically. Do not over-explain. "

    # --- Phase 4: Options (DO NOT REBOOK) ---
    "Do NOT confirm any rebooking automatically. "
    "Present 2 to 3 concrete options clearly. Each option must include the new flight time, "
    "routing, and any upgrade or compensation. "
    "Ask the passenger which option they prefer before taking any action. "

    # --- Phase 5: Baggage Handling ---
    "If the passenger asks about their bags, call the lookup_baggage tool immediately. "
    "Report the exact number of bags and whether they have been automatically transferred. "
    "Be specific — name the count, not just 'your luggage'. "

    # --- Tone ---
    "Always be human, concise, and proactive. Never list more than 3 items in one breath. "
    "Do not use filler phrases like 'Certainly!' or 'Of course!'. "
)
```

- [ ] **Step 2: Update on-connect system message**

Find inside `on_client_connected`:
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
git commit -m "feat: Aria persona, phased system prompt referencing pre-call brief"
```

---

## Verification — End-to-End Smoke Test

1. Wipe and re-seed Neo4j (or use `NEO4J_SEED=true`):
   ```bash
   cd D:/vocare/v2/pipecat/examples/vocare
   NEO4J_SEED=true python bot.py
   ```

2. Open http://localhost:7860, enable Knowledge Graph, Connect.

3. Say **"QF-7731"** — verify:
   - Graph loads: QF107 (red ⚡ alert), QF821 (red/amber alert), QF815 (normal blue), QF109 purple Rebooking, 4 green Baggage nodes, 3 indigo Event nodes animating in sequence (TRIGGERED chain visible)
   - Agent says "Aria", references the hydraulic fault and cascade, does NOT offer to rebook yet

4. Say **"What are my options?"** — verify QF109 node pulses (keyword: "qf109" / "tonight" / "options")

5. Say **"What about my bags?"** — verify all 4 bag nodes pulse cyan simultaneously

6. Say **"I'm Von, flying Sydney to San Francisco"** (name+route lookup) — verify `lookup_customer` resolves QF-7731 via SYD+SFO codes
