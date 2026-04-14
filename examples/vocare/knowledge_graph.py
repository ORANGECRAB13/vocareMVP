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
            MERGE (c:Customer {booking_ref: 'QF-8200'})
            SET c.name = 'Jack Smith',
                c.phone = '+61412345678',
                c.loyalty_tier = 'Silver'

            // ── Channel hubs ───────────────────────────────────────────────
            MERGE (ch1:Channel {name: 'CRM'})
            SET ch1.display_name = 'CRM Channel'

            MERGE (ch2:Channel {name: 'Communications'})
            SET ch2.display_name = 'Communications Channel'

            MERGE (ch3:Channel {name: 'Baggage Handling'})
            SET ch3.display_name = 'Baggage Handling Channel'

            MERGE (ch4:Channel {name: 'CodeShare Flights'})
            SET ch4.display_name = 'CodeShare Flights Channel'

            // ── CRM sub-nodes: original booking + past interactions ────────
            MERGE (f1:FlightOperation {flight_number: 'QF82'})
            SET f1.route = 'SYD-MEL',
                f1.status = 'CANCELLED',
                f1.reason = 'engineering fault on aircraft',
                f1.scheduled_time = '2026-04-14T22:30',
                f1.description = 'Sydney to Melbourne, cancelled — engineering hold'

            MERGE (crm1:CRMRecord {id: 'crm-001'})
            SET crm1.type = 'Loyalty Query',
                crm1.date = 'Dec 2025',
                crm1.description = 'Points balance — 12,400 pts'

            MERGE (crm2:CRMRecord {id: 'crm-002'})
            SET crm2.type = 'Seat Upgrade',
                crm2.date = 'Jan 2026',
                crm2.description = 'Business class on QF1'

            MERGE (crm3:CRMRecord {id: 'crm-003'})
            SET crm3.type = 'Baggage Policy',
                crm3.date = 'Mar 2026',
                crm3.description = 'Excess allowance — 32 kg approved'

            // ── Communications sub-nodes ───────────────────────────────────
            MERGE (comm1:Communication {channel: 'Email', sent_at: '2026-04-14T22:20'})
            SET comm1.message = 'Cancellation notice — QF82 SYD to MEL'

            MERGE (comm2:Communication {channel: 'SMS', sent_at: '2026-04-14T22:46'})
            SET comm2.message = 'Hotel voucher + $50 meal — Rydges Airport Hotel'

            MERGE (comm3:Communication {channel: 'Phone', sent_at: '2026-04-14T22:50'})
            SET comm3.message = 'Outbound call — no answer'

            // ── Baggage sub-nodes ──────────────────────────────────────────
            MERGE (b1:Baggage {tag: 'QF82001'})
            SET b1.destination = 'MEL',
                b1.location = 'Terminal 3 Secure Facility',
                b1.last_scan = 'Carousel 4 — intercepted before loading',
                b1.status = 'held_secure',
                b1.weight_kg = 24.5

            MERGE (b2:Baggage {tag: 'QF82002'})
            SET b2.destination = 'MEL',
                b2.location = 'Terminal 3 Secure Facility',
                b2.last_scan = 'Carousel 4 — intercepted before loading',
                b2.status = 'held_secure',
                b2.weight_kg = 18.0

            // ── CodeShare Flights sub-nodes ────────────────────────────────
            MERGE (r1:Rebooking {alt_flight: 'QF83'})
            SET r1.route = 'SYD-MEL',
                r1.departure = '2026-04-15T06:00',
                r1.seats_available = 1,
                r1.cabin = 'economy',
                r1.note = 'rescheduled — engineering delay'

            MERGE (r2:Rebooking {alt_flight: 'VA850'})
            SET r2.route = 'SYD-MEL',
                r2.departure = '2026-04-15T07:30',
                r2.seats_available = 3,
                r2.cabin = 'economy',
                r2.note = 'Virgin codeshare'

            MERGE (r3:Rebooking {alt_flight: 'QF85'})
            SET r3.route = 'SYD-MEL',
                r3.departure = '2026-04-15T09:45',
                r3.seats_available = 5,
                r3.cabin = 'economy',
                r3.note = 'morning departure'

            // ── Channel membership ─────────────────────────────────────────
            MERGE (c)-[:HAS_CHANNEL {source: 'Salesforce CRM'}]->(ch1)
            MERGE (c)-[:HAS_CHANNEL {source: 'Qantas Digital Services'}]->(ch2)
            MERGE (c)-[:HAS_CHANNEL {source: 'Terminal RFID System'}]->(ch3)
            MERGE (c)-[:HAS_CHANNEL {source: 'Revenue Management'}]->(ch4)

            MERGE (ch1)-[:CONTAINS]->(f1)
            MERGE (ch1)-[:CONTAINS]->(crm1)
            MERGE (ch1)-[:CONTAINS]->(crm2)
            MERGE (ch1)-[:CONTAINS]->(crm3)

            MERGE (ch2)-[:CONTAINS]->(comm1)
            MERGE (ch2)-[:CONTAINS]->(comm2)
            MERGE (ch2)-[:CONTAINS]->(comm3)

            MERGE (ch3)-[:CONTAINS]->(b1)
            MERGE (ch3)-[:CONTAINS]->(b2)

            MERGE (ch4)-[:CONTAINS]->(r1)
            MERGE (ch4)-[:CONTAINS]->(r2)
            MERGE (ch4)-[:CONTAINS]->(r3)

            MERGE (b1)-[:CHECKED_ON]->(f1)
            MERGE (b2)-[:CHECKED_ON]->(f1)

            // ── Event chain (temporal provenance — direct from Customer) ───
            MERGE (e1:Event {id: 'evt-001'})
            SET e1.type = 'FLIGHT_CANCELLED',
                e1.timestamp = '2026-04-14T22:15',
                e1.description = 'QF82 grounded — engineering fault on aircraft'

            MERGE (e2:Event {id: 'evt-002'})
            SET e2.type = 'BAGGAGE_INTERCEPTED',
                e2.timestamp = '2026-04-14T22:25',
                e2.description = 'Bags intercepted at Carousel 4 — held in Terminal 3 Secure'

            MERGE (e3:Event {id: 'evt-003'})
            SET e3.type = 'ACCOMMODATION_ARRANGED',
                e3.timestamp = '2026-04-14T22:40',
                e3.description = 'Rydges Airport Hotel booked — engineering delay coverage'

            MERGE (e4:Event {id: 'evt-004'})
            SET e4.type = 'PASSENGER_NOTIFIED',
                e4.timestamp = '2026-04-14T22:46',
                e4.description = 'SMS sent: hotel voucher + $50 meal allowance'

            MERGE (e1)-[:TRIGGERED]->(e2)
            MERGE (e2)-[:TRIGGERED]->(e3)
            MERGE (e3)-[:TRIGGERED]->(e4)
            MERGE (c)-[:EXPERIENCED]->(e1)

            // ── CallContext (call-readiness brief) ─────────────────────────
            MERGE (ctx:CallContext {booking_ref: 'QF-8200'})
            SET ctx.primary_issue = 'QF82 SYD to MEL cancelled — engineering fault on aircraft',
                ctx.recommended_action = 'Rebook to QF83 06:00 tomorrow — hotel already arranged',
                ctx.loyalty_flag = 'Silver — standard engineering delay entitlements apply',
                ctx.baggage_status = 'Both bags held in Terminal 3 Secure, auto-load to rescheduled flight',
                ctx.urgency = 'HIGH'

            MERGE (c)-[:HAS_CALL_CONTEXT]->(ctx)
            """
        )
    logger.info(
        "Neo4j graph seeded with Jack Smith / QF-8200 channel-based context graph"
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
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'CRM'})-[:CONTAINS]->(f:FlightOperation)
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'Baggage Handling'})-[:CONTAINS]->(b:Baggage)
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'CodeShare Flights'})-[:CONTAINS]->(r:Rebooking)
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'Communications'})-[:CONTAINS]->(comm:Communication)
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

    # Also check if the input looks like a flight number (e.g. QF82)
    flight_num_match = re.match(r"^[A-Z]{1,3}\d+$", route_upper.strip())

    with driver.session() as session:
        if codes:
            # Match by name + any flight with matching route codes (via CRM channel)
            route_pattern = "-".join(codes) if len(codes) >= 2 else codes[0]
            result = session.run(
                """
                MATCH (c:Customer)-[:HAS_CHANNEL]->(:Channel {name: 'CRM'})-[:CONTAINS]->(f:FlightOperation)
                WHERE toLower(c.name) CONTAINS toLower($name)
                  AND f.route CONTAINS $route_pattern
                RETURN c.booking_ref AS booking_ref
                LIMIT 1
                """,
                name=customer_name.strip(),
                route_pattern=route_pattern,
            )
        elif flight_num_match:
            # Match by name + flight number directly (e.g. "QF82") via CRM channel
            result = session.run(
                """
                MATCH (c:Customer)-[:HAS_CHANNEL]->(:Channel {name: 'CRM'})-[:CONTAINS]->(f:FlightOperation)
                WHERE toLower(c.name) CONTAINS toLower($name)
                  AND toUpper(f.flight_number) = $flight_num
                RETURN c.booking_ref AS booking_ref
                LIMIT 1
                """,
                name=customer_name.strip(),
                flight_num=route_upper.strip(),
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
            OPTIONAL MATCH (c)-[hch:HAS_CHANNEL]->(ch:Channel)
            OPTIONAL MATCH (ch)-[:CONTAINS]->(sub)
            OPTIONAL MATCH (c)-[:EXPERIENCED]->(e1:Event)
            OPTIONAL MATCH (e1)-[:TRIGGERED*0..5]->(echain:Event)
            RETURN c,
                   collect(DISTINCT {ch: ch, source: hch.source}) AS channels,
                   collect(DISTINCT {ch_name: ch.name, sub: sub, sub_labels: labels(sub)}) AS sub_nodes,
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

        # Channel hub nodes
        channel_order = ["CRM", "Communications", "Baggage Handling", "CodeShare Flights"]
        channel_source_map = {
            "CRM": "Salesforce CRM",
            "Communications": "Qantas Digital Services",
            "Baggage Handling": "Terminal RFID System",
            "CodeShare Flights": "Revenue Management",
        }
        seen_channels: set = set()
        sorted_channels = sorted(
            record["channels"],
            key=lambda item: (
                channel_order.index(item["ch"]["name"])
                if item["ch"] and item["ch"]["name"] in channel_order
                else 999
            ),
        )
        for item in sorted_channels:
            ch = item["ch"]
            if ch is None or ch["name"] in seen_channels:
                continue
            seen_channels.add(ch["name"])
            ch_id = f"channel-{ch['name'].lower().replace(' ', '-')}"
            source = item.get("source") or channel_source_map.get(ch["name"], ch["name"])
            nodes.append({
                "id": ch_id,
                "type": "Channel",
                "label": ch.get("display_name", ch["name"]),
                "sublabel": source,
            })
            edges.append({"source": cust_id, "target": ch_id, "label": source})

        # Sub-nodes under each channel
        # Track seen sub-nodes by id to avoid duplicates from multi-OPTIONAL-MATCH
        seen_sub: set = set()
        bag_tags_to_flight: Dict[str, str] = {}  # tag -> flight_number for CHECKED_ON edges
        # Sort sub-nodes so CRM flight comes first (for LAYOUT_MAP slot assignment)
        sub_items = [
            item for item in record["sub_nodes"]
            if item["sub"] is not None
        ]

        for item in sub_items:
            ch_name = item["ch_name"]
            sub = item["sub"]
            sub_labels = item["sub_labels"] or []
            if sub is None:
                continue

            # Determine primary label (first non-redundant one)
            known_types = {
                "FlightOperation", "CRMRecord", "Communication", "Baggage", "Rebooking"
            }
            node_type = next((lbl for lbl in sub_labels if lbl in known_types), None)
            if node_type is None:
                continue

            ch_id = f"channel-{ch_name.lower().replace(' ', '-')}"

            if node_type == "FlightOperation":
                fid = f"flight-{sub['flight_number']}"
                if fid in seen_sub:
                    continue
                seen_sub.add(fid)
                status = sub["status"].upper()
                route = friendly_route(sub["route"])
                if status == "CANCELLED":
                    status_text = f"Cancelled \u2014 {sub.get('reason', 'unknown')}"
                elif status == "DISRUPTED":
                    status_text = f"Disrupted \u2014 {sub.get('reason', 'missed connection')}"
                elif status == "OPERATED":
                    status_text = "Arrived on time"
                else:
                    status_text = status
                nodes.append({
                    "id": fid,
                    "type": "FlightOperation",
                    "label": f"{sub['flight_number']} \u00b7 {route}",
                    "sublabel": status_text,
                    "alert": status in ("CANCELLED", "DISRUPTED"),
                })
                edges.append({"source": ch_id, "target": fid, "label": "CONTAINS"})

            elif node_type == "CRMRecord":
                rid = f"crm-{sub['id']}"
                if rid in seen_sub:
                    continue
                seen_sub.add(rid)
                nodes.append({
                    "id": rid,
                    "type": "CRMRecord",
                    "label": sub["type"],
                    "sublabel": f"{sub['date']} \u00b7 {sub['description']}",
                })
                edges.append({"source": ch_id, "target": rid, "label": "CONTAINS"})

            elif node_type == "Communication":
                cid = f"comm-{sub['channel']}"
                if cid in seen_sub:
                    continue
                seen_sub.add(cid)
                time_str = friendly_time(sub["sent_at"])
                nodes.append({
                    "id": cid,
                    "type": "Communication",
                    "label": f"{sub['channel']}",
                    "sublabel": f"{time_str} \u00b7 {sub['message']}",
                })
                edges.append({"source": ch_id, "target": cid, "label": "CONTAINS"})

            elif node_type == "Baggage":
                bid = f"baggage-{sub['tag']}"
                if bid in seen_sub:
                    continue
                seen_sub.add(bid)
                location = sub["location"]
                last_scan = sub.get("last_scan", "")
                status_str = (
                    f"{location}"
                    + (f" \u00b7 {last_scan}" if last_scan else "")
                )
                nodes.append({
                    "id": bid,
                    "type": "Baggage",
                    "label": f"Bag {sub['tag']}",
                    "sublabel": status_str,
                })
                edges.append({"source": ch_id, "target": bid, "label": "CONTAINS"})
                # Collect for CHECKED_ON edge — we'll resolve flight_number separately
                bag_tags_to_flight[sub["tag"]] = "QF82"  # known from seed

            elif node_type == "Rebooking":
                rbid = f"rebooking-{sub['alt_flight']}"
                if rbid in seen_sub:
                    continue
                seen_sub.add(rbid)
                route = friendly_route(sub["route"])
                time_str = friendly_time(sub["departure"])
                seats = sub["seats_available"]
                seat_word = "seat" if seats == 1 else "seats"
                note = f" \u00b7 {sub['note']}" if sub.get("note") else ""
                nodes.append({
                    "id": rbid,
                    "type": "Rebooking",
                    "label": f"{sub['alt_flight']} \u00b7 {route}",
                    "sublabel": f"{time_str} \u00b7 {seats} {seat_word}{note}",
                })
                edges.append({"source": ch_id, "target": rbid, "label": "CONTAINS"})

        # Baggage → FlightOperation edges (CHECKED_ON)
        for tag, flight_num in bag_tags_to_flight.items():
            flight_node_id = f"flight-{flight_num}"
            if flight_node_id in {n["id"] for n in nodes}:
                edges.append({
                    "source": f"baggage-{tag}",
                    "target": flight_node_id,
                    "label": "Checked on",
                })

        # Event chain nodes (sorted by timestamp)
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

    # Traverse in domain order: channels first, then their sub-nodes, then event chain
    traversal_order = [
        "Salesforce CRM",
        "Qantas Digital Services",
        "Terminal RFID System",
        "Revenue Management",
        "CONTAINS",
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

        if ntype == "Channel":
            # Channel hubs are navigational containers — skip keyword mapping
            continue

        elif ntype == "Customer":
            # Match on first name, full name
            name = node.get("label", "")
            if name:
                mapping[name.lower()] = nid
                first = name.split()[0].lower()
                if len(first) > 2:
                    mapping[first] = nid

        elif ntype == "CRMRecord":
            # Match on CRM record type keywords
            label = node.get("label", "").lower()
            sublabel = node.get("sublabel", "").lower()
            if "loyalty" in label:
                mapping["loyalty"] = nid
                mapping["points"] = nid
            elif "upgrade" in label:
                mapping["upgrade"] = nid
                mapping["business class"] = nid
            elif "baggage policy" in label:
                mapping["policy"] = nid
                mapping["allowance"] = nid
            # Map date keywords from sublabel
            for word in sublabel.split():
                if len(word) > 3 and word.isalpha():
                    mapping[word] = nid

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
                mapping["tomorrow"] = nid
                mapping["6am"] = nid
                mapping["06:00"] = nid
                mapping["morning flight"] = nid
                mapping["qf83"] = nid

        elif ntype == "Communication":
            # Match on channel name
            label = node.get("label", "").lower()
            if "hotel" in label:
                mapping["rydges"] = nid
                mapping["hotel"] = nid
                mapping["accommodation"] = nid
                mapping["overnight"] = nid
                mapping["room"] = nid
            elif "sms" in label:
                mapping["sms"] = nid
                mapping["text message"] = nid
                mapping["voucher"] = nid
                mapping["meal"] = nid
                mapping["fifty"] = nid
                mapping["$50"] = nid
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
                mapping["engineering"] = nid
            elif "intercepted" in etype or "baggage" in etype:
                mapping["intercepted"] = nid
                mapping["carousel"] = nid
                mapping["rfid"] = nid
            elif "accommodation" in etype or "hotel" in etype:
                mapping["arranged"] = nid
                mapping["booked"] = nid
            elif "notified" in etype or "passenger" in etype:
                mapping["sent"] = nid
                mapping["digital"] = nid

    return mapping


def build_path_map(graph: Dict) -> Dict[str, Dict]:
    """Build channel path definitions for sequential graph traversal animation.

    Maps keywords the agent is likely to say when discussing a channel to a
    ``{steps, color}`` dict consumed by the frontend ``highlightPath`` method.
    Path keywords take priority over individual ``highlight`` events so the
    whole channel animates when the agent discusses it broadly.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.

    Returns:
        Dict mapping lowercase keyword/phrase to
        ``{"steps": [nodeId, ...], "color": "#hex"}``.
    """
    if not graph:
        return {}

    # Colors must match the deployed frontend TYPE_COLORS + channel-key convention
    CHANNEL_COLORS = {
        "crm": "#fbbf24",
        "communications": "#f97316",
        "baggage-handling": "#10b981",
        "codeshare-flights": "#8b5cf6",
    }

    # Keywords that indicate the agent is talking about a whole channel
    CHANNEL_KEYWORDS: Dict[str, List[str]] = {
        "crm": [
            "crm", "salesforce", "customer record", "past booking",
            "your history", "previous interaction",
        ],
        "communications": [
            "communication", "notification", "notified", "we contacted",
            "we've contacted", "sent you", "reached out",
            "accommodation", "hotel", "voucher",
        ],
        "baggage-handling": [
            "baggage", "bag", "bags", "luggage", "suitcase",
        ],
        "codeshare-flights": [
            "codeshare", "alternative flight", "flight options",
            "rebooking options", "available seats", "rebook you",
        ],
    }

    node_map = {n["id"]: n for n in graph["nodes"]}

    customer_id = next(
        (n["id"] for n in graph["nodes"] if n["type"] == "Customer"), None
    )
    if not customer_id:
        return {}

    # Build channel → ordered list of sub-node IDs from edges
    channel_children: Dict[str, List[str]] = {}
    for edge in graph.get("edges", []):
        src = edge["source"]
        src_node = node_map.get(src)
        if src_node and src_node["type"] == "Channel":
            channel_children.setdefault(src, []).append(edge["target"])

    path_map: Dict[str, Dict] = {}

    for node in graph["nodes"]:
        if node["type"] != "Channel":
            continue
        ch_id = node["id"]
        ch_key = ch_id.replace("channel-", "")
        color = CHANNEL_COLORS.get(ch_key, "#64748b")
        sub_ids = channel_children.get(ch_id, [])
        path_def = {"steps": [customer_id, ch_id] + sub_ids, "color": color}

        for kw in CHANNEL_KEYWORDS.get(ch_key, []):
            path_map[kw] = path_def

    return path_map


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
            MATCH (c:Customer {booking_ref: $ref})
                  -[:HAS_CHANNEL]->(:Channel {name: 'Baggage Handling'})
                  -[:CONTAINS]->(b:Baggage)
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
            location = b.get("location", "unknown location")
            last_scan = b.get("last_scan", "")
            if status == "held_secure":
                status_str = f"held in {location}"
                if last_scan:
                    status_str += f" — last RFID scan: {last_scan}"
            elif status == "transferred":
                status_str = "auto-transferred to rescheduled flight"
            else:
                status_str = status
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
