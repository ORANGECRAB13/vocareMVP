"""Neo4j knowledge graph integration for proactive customer context.

Provides graph seeding with mock Qantas flight disruption data and
async context retrieval for use at call connection time.
"""

import asyncio
import json
from typing import Dict, List, Optional

from loguru import logger


def seed_graph(driver):
    """Populate Neo4j with mock Qantas flight disruption data.

    Idempotent — uses MERGE to avoid duplicates. Safe to call on every startup.

    Args:
        driver: Neo4j driver instance.
    """
    with driver.session() as session:
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
    logger.info(
        "Neo4j graph seeded with Von / QF-7731 context graph"
        " (temporal + call-readiness + provenance)"
    )


def _query_customer_context_sync(driver, booking_ref: str) -> Optional[str]:
    """Synchronous graph query — called via asyncio.to_thread.

    Args:
        driver: Neo4j driver instance.
        booking_ref: Customer booking reference to look up.

    Returns:
        Formatted situation summary string, or None if customer not found.
    """
    with driver.session() as session:
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

        record = result.single()
        if not record or record["c"] is None:
            return None

        customer = record["c"]
        flights = record["flights"]
        baggage = record["baggage"]
        rebooking_options = record["rebooking_options"]
        communications = record["communications"]

        lines = []

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

        lines.append("=== CUSTOMER SITUATION SUMMARY ===")
        lines.append("")
        lines.append(
            f"Customer: {customer['name']}, "
            f"Booking: {customer['booking_ref']}, "
            f"Loyalty: {customer['loyalty_tier']}, "
            f"Phone: {customer['phone']}"
        )

        if flights:
            lines.append("")
            lines.append("FLIGHTS:")
            for f in flights:
                status = f["status"].upper()
                reason = f" ({f['reason']})" if f.get("reason") else ""
                lines.append(
                    f"  - {f['flight_number']} {f['route']}: "
                    f"{status}{reason}, scheduled {f['scheduled_time']}"
                )

        if baggage:
            lines.append("")
            lines.append("BAGGAGE:")
            for b in baggage:
                lines.append(
                    f"  - Tag {b['tag']}: destination {b['destination']}, "
                    f"currently at {b['location']}, status: {b['status']}"
                )

        if rebooking_options:
            lines.append("")
            lines.append("AVAILABLE REBOOKING OPTIONS:")
            for r in rebooking_options:
                note = f" ({r['note']})" if r.get("note") else ""
                lines.append(
                    f"  - {r['alt_flight']} {r['route']}: "
                    f"departs {r['departure']}, "
                    f"{r['seats_available']} {r['cabin']} seat(s) available{note}"
                )

        if communications:
            lines.append("")
            lines.append("PRIOR COMMUNICATIONS SENT:")
            for comm in communications:
                lines.append(f"  - {comm['channel']} at {comm['sent_at']}: {comm['message']}")

        return "\n".join(lines)


async def query_customer_context(driver, booking_ref: str) -> Optional[str]:
    """Query Neo4j for full customer context, async-safe.

    Args:
        driver: Neo4j driver instance.
        booking_ref: Customer booking reference to look up.

    Returns:
        Formatted situation summary string, or None if customer not found.
    """
    return await asyncio.to_thread(_query_customer_context_sync, driver, booking_ref)


def _query_booking_by_name_and_route_sync(
    driver, customer_name: str, route: str
) -> Optional[str]:
    """Find a booking reference by customer name and flight route.

    Args:
        driver: Neo4j driver instance.
        customer_name: Full or partial customer name (case-insensitive).
        route: Flight route like 'SYD-AKL' or city names like 'Sydney Auckland'.

    Returns:
        Booking reference string, or None if not found.
    """
    # Normalize route — accept city names or codes
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
    route_upper = route.upper().strip()
    route_lower = route.lower().strip()

    # Try to convert city names to codes for matching
    route_codes = route_upper
    for city, code in city_to_code.items():
        route_lower = route_lower.replace(city, code.lower())
    # Extract just the airport codes (3-letter sequences)
    import re

    codes = re.findall(r"[A-Z]{3}", route_lower.upper())

    with driver.session() as session:
        if codes:
            # Match by name + any flight with matching route codes
            route_pattern = "-".join(codes) if len(codes) >= 2 else codes[0]
            result = session.run(
                """
                MATCH (c:Customer)-[:HAS_FLIGHT]->(f:FlightOperation)
                WHERE toLower(c.name) CONTAINS toLower($name)
                  AND f.route CONTAINS $route_pattern
                RETURN c.booking_ref AS booking_ref
                LIMIT 1
                """,
                name=customer_name.strip(),
                route_pattern=route_pattern,
            )
        else:
            # Just match by name
            result = session.run(
                """
                MATCH (c:Customer)
                WHERE toLower(c.name) CONTAINS toLower($name)
                RETURN c.booking_ref AS booking_ref
                LIMIT 1
                """,
                name=customer_name.strip(),
            )

        record = result.single()
        if record and record["booking_ref"]:
            return record["booking_ref"]
        return None


async def query_booking_by_name_and_route(
    driver, customer_name: str, route: str
) -> Optional[str]:
    """Find booking reference by customer name and flight route, async-safe.

    Args:
        driver: Neo4j driver instance.
        customer_name: Full or partial customer name.
        route: Flight route (codes or city names).

    Returns:
        Booking reference string, or None if not found.
    """
    return await asyncio.to_thread(
        _query_booking_by_name_and_route_sync, driver, customer_name, route
    )


def _query_graph_structure_sync(driver, booking_ref: str) -> Optional[Dict]:
    """Query Neo4j and return graph structure as nodes + edges for visualization.

    Args:
        driver: Neo4j driver instance.
        booking_ref: Customer booking reference to look up.

    Returns:
        Dict with "nodes" and "edges" lists, or None if customer not found.
    """
    with driver.session() as session:
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
            "sublabel": (
                f"Booking {customer['booking_ref']}"
                f"  \u00b7  {customer['loyalty_tier']} member"
            ),
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

        # Event chain nodes (temporal layer — sorted by timestamp for correct chain order)
        seen_events: set = set()
        prev_event_id = None
        sorted_events = sorted(
            (e for e in record["events"] if e is not None),
            key=lambda e: e.get("timestamp", ""),
        )
        for e in sorted_events:
            if e["id"] in seen_events:
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
                edges.append({"source": cust_id, "target": eid, "label": "Experienced"})
            else:
                edges.append({"source": prev_event_id, "target": eid, "label": "Triggered"})
            prev_event_id = eid

        return {"nodes": nodes, "edges": edges}


async def query_graph_structure(driver, booking_ref: str) -> Optional[Dict]:
    """Query Neo4j for graph structure (nodes + edges), async-safe.

    Args:
        driver: Neo4j driver instance.
        booking_ref: Customer booking reference to look up.

    Returns:
        Dict with "nodes" and "edges" lists, or None if customer not found.
    """
    return await asyncio.to_thread(_query_graph_structure_sync, driver, booking_ref)


def build_traversal_sequence(graph: Dict) -> List[Dict]:
    """Build an ordered traversal sequence for animating graph exploration.

    The sequence starts at the Customer node, then fans out by relationship type
    in the order: flights, baggage, rebooking, communications, then CHECKED_ON.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.

    Returns:
        List of event dicts for the frontend to animate.
    """
    if not graph:
        return []

    events: List[Dict] = []
    node_ids = {n["id"] for n in graph["nodes"]}
    edge_by_label: Dict[str, List[Dict]] = {}
    for e in graph["edges"]:
        edge_by_label.setdefault(e["label"], []).append(e)

    # Find customer node
    customer_id = None
    for n in graph["nodes"]:
        if n["type"] == "Customer":
            customer_id = n["id"]
            break

    if not customer_id:
        return []

    events.append({"type": "activate", "nodeId": customer_id})

    # Traverse in domain order
    traversal_order = [
        "Qantas OpsDB",
        "Baggage Handling System",
        "Inventory API",
        "Notified",
        "Checked on",
        "Experienced",
        "Triggered",
    ]

    for label in traversal_order:
        for edge in edge_by_label.get(label, []):
            events.append(
                {
                    "type": "traverse",
                    "fromId": edge["source"],
                    "toId": edge["target"],
                    "label": edge["label"],
                }
            )

    return events


def build_keyword_map(graph: Dict) -> Dict[str, str]:
    """Build a keyword-to-nodeId mapping for conversation-aware highlighting.

    Maps words/phrases the LLM is likely to say to the graph node IDs they
    refer to. Used by the observer to detect which nodes are being discussed.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.

    Returns:
        Dict mapping lowercase keyword/phrase to node ID.
    """
    if not graph:
        return {}

    mapping: Dict[str, str] = {}

    for node in graph["nodes"]:
        nid = node["id"]
        ntype = node["type"]

        if ntype == "Customer":
            # Match on first name, full name
            name = node.get("label", "")
            if name:
                mapping[name.lower()] = nid
                first = name.split()[0].lower()
                if len(first) > 2:
                    mapping[first] = nid

        elif ntype == "FlightOperation":
            # Match on flight number (QF451, QF452) and city names in label
            label = node.get("label", "")
            # Extract flight number (first token before the dot-separator)
            flight_num = label.split("\u00b7")[0].strip() if "\u00b7" in label else label
            if flight_num:
                mapping[flight_num.lower()] = nid
            # Extract city names from label
            if "\u00b7" in label:
                route_part = label.split("\u00b7")[1].strip().lower()
                for city in route_part.replace(" to ", ",").split(","):
                    city = city.strip()
                    if len(city) > 3:
                        mapping[city] = nid
            # Sublabel keywords
            sublabel = node.get("sublabel", "").lower()
            if "cancelled" in sublabel or "cancel" in sublabel:
                mapping["cancelled"] = nid
                mapping["cancellation"] = nid
                mapping["canceled"] = nid
        elif ntype == "Baggage":
            # Match on "bag", "baggage", "luggage", "suitcase"
            mapping["baggage"] = nid
            mapping["luggage"] = nid
            mapping["suitcase"] = nid
            # Only map "bag" / "bags" to first baggage node to avoid flicker
            if "bag" not in mapping:
                mapping["bag"] = nid
                mapping["bags"] = nid

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

        elif ntype == "Communication":
            # Match on channel name
            label = node.get("label", "").lower()
            if "sms" in label:
                mapping["sms"] = nid
                mapping["text message"] = nid
            elif "email" in label:
                mapping["email"] = nid
            elif "push" in label or "app" in label:
                mapping["app"] = nid
                mapping["notification"] = nid
                mapping["push"] = nid
            # General comms keywords
            if "notified" not in mapping:
                mapping["notified"] = nid
                mapping["contacted"] = nid
                mapping["informed"] = nid

        elif ntype == "Event":
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

    return mapping


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
