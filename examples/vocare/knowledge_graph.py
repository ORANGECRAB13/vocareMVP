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
            // Customer
            MERGE (c:Customer {booking_ref: 'QF-8842'})
            SET c.name = 'Sarah Mitchell',
                c.phone = '+61412345678',
                c.loyalty_tier = 'Gold'

            // Flight operations
            MERGE (f1:FlightOperation {flight_number: 'QF451'})
            SET f1.route = 'SYD-AKL',
                f1.status = 'operated',
                f1.reason = NULL,
                f1.scheduled_time = '2026-04-08T14:00',
                f1.description = 'Sydney to Auckland, arrived on time'

            MERGE (f2:FlightOperation {flight_number: 'QF452'})
            SET f2.route = 'AKL-LAX',
                f2.status = 'CANCELLED',
                f2.reason = 'weather/volcanic ash',
                f2.scheduled_time = '2026-04-08T23:30',
                f2.description = 'Auckland to Los Angeles, cancelled due to volcanic ash'

            // Baggage
            MERGE (b1:Baggage {tag: 'QFBAG-991201'})
            SET b1.destination = 'LAX',
                b1.location = 'AKL terminal',
                b1.status = 'held'

            // Rebooking options
            MERGE (r1:Rebooking {alt_flight: 'QF454'})
            SET r1.route = 'AKL-LAX',
                r1.departure = '2026-04-09T11:00',
                r1.seats_available = 3,
                r1.cabin = 'economy'

            // Communications
            MERGE (comm1:Communication {channel: 'SMS', sent_at: '2026-04-08T18:00'})
            SET comm1.message = 'Your flight QF452 AKL-LAX has been cancelled due to weather. Please contact us for rebooking.'

            MERGE (comm2:Communication {channel: 'Email', sent_at: '2026-04-08T18:05'})
            SET comm2.message = 'Detailed cancellation notice with rebooking link'

            // Relationships
            MERGE (c)-[:HAS_FLIGHT]->(f1)
            MERGE (c)-[:HAS_FLIGHT]->(f2)
            MERGE (c)-[:HAS_BAGGAGE]->(b1)
            MERGE (c)-[:HAS_REBOOKING_OPTION]->(r1)
            MERGE (c)-[:RECEIVED_COMM]->(comm1)
            MERGE (c)-[:RECEIVED_COMM]->(comm2)
            MERGE (b1)-[:CHECKED_ON]->(f2)
            """
        )
    logger.info("Neo4j graph seeded with Qantas flight disruption data")


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
            RETURN c,
                   collect(DISTINCT f) AS flights,
                   collect(DISTINCT b) AS baggage,
                   collect(DISTINCT r) AS rebooking_options,
                   collect(DISTINCT comm) AS communications
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
            OPTIONAL MATCH (c)-[:HAS_FLIGHT]->(f:FlightOperation)
            OPTIONAL MATCH (c)-[:HAS_BAGGAGE]->(b:Baggage)
            OPTIONAL MATCH (c)-[:HAS_REBOOKING_OPTION]->(r:Rebooking)
            OPTIONAL MATCH (c)-[:RECEIVED_COMM]->(comm:Communication)
            OPTIONAL MATCH (b)-[co:CHECKED_ON]->(bf:FlightOperation)
            RETURN c,
                   collect(DISTINCT f) AS flights,
                   collect(DISTINCT b) AS baggage,
                   collect(DISTINCT r) AS rebookings,
                   collect(DISTINCT comm) AS comms,
                   collect(DISTINCT {bag_tag: b.tag, flight_num: bf.flight_number}) AS bag_flights
            """,
            ref=booking_ref,
        )

        record = result.single()
        if not record or record["c"] is None:
            return None

        customer = record["c"]
        nodes: List[Dict] = []
        edges: List[Dict] = []

        # Human-friendly route names
        city_names = {
            "SYD": "Sydney",
            "AKL": "Auckland",
            "LAX": "Los Angeles",
            "MEL": "Melbourne",
            "BNE": "Brisbane",
        }

        def friendly_route(route: str) -> str:
            parts = route.split("-")
            return " to ".join(city_names.get(p, p) for p in parts)

        def friendly_time(iso: str) -> str:
            """Turn '2026-04-09T11:00' into 'Apr 9, 11:00 AM'."""
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(iso)
                # %#d / %#I for Windows, %-d / %-I for Unix — try both
                try:
                    return dt.strftime("%b %#d, %#I:%M %p")
                except ValueError:
                    return dt.strftime("%b %-d, %-I:%M %p")
            except Exception:
                return iso

        cust_id = f"customer-{customer['booking_ref']}"
        nodes.append(
            {
                "id": cust_id,
                "type": "Customer",
                "label": customer["name"],
                "sublabel": f"Booking {customer['booking_ref']}  \u00b7  {customer['loyalty_tier']} member",
            }
        )

        for f in record["flights"]:
            fid = f"flight-{f['flight_number']}"
            status = f["status"].upper()
            route = friendly_route(f["route"])
            if status == "CANCELLED":
                status_text = f"Cancelled \u2014 {f.get('reason', 'unknown')}"
            elif status == "OPERATED":
                status_text = "Arrived on time"
            else:
                status_text = status
            nodes.append(
                {
                    "id": fid,
                    "type": "FlightOperation",
                    "label": f"{f['flight_number']} \u00b7 {route}",
                    "sublabel": status_text,
                    "alert": status == "CANCELLED",
                }
            )
            edges.append({"source": cust_id, "target": fid, "label": "Booked flight"})

        bag_count = len(record["baggage"])
        for i, b in enumerate(record["baggage"], 1):
            bid = f"baggage-{b['tag']}"
            location = b["location"].replace("AKL terminal", "Auckland terminal")
            status = "Held in transit" if b["status"] == "held" else b["status"]
            bag_label = "Checked Baggage" if bag_count == 1 else f"Bag {i}"
            nodes.append(
                {
                    "id": bid,
                    "type": "Baggage",
                    "label": bag_label,
                    "sublabel": f"{location} \u00b7 {status}",
                }
            )
            edges.append({"source": cust_id, "target": bid, "label": "Checked bag"})

        for r in record["rebookings"]:
            rid = f"rebooking-{r['alt_flight']}"
            route = friendly_route(r["route"])
            time = friendly_time(r["departure"])
            seats = r["seats_available"]
            seat_word = "seat" if seats == 1 else "seats"
            note = f" ({r['note']})" if r.get("note") else ""
            nodes.append(
                {
                    "id": rid,
                    "type": "Rebooking",
                    "label": f"{r['alt_flight']} \u00b7 {route}",
                    "sublabel": f"{time} \u00b7 {seats} {seat_word}{note}",
                }
            )
            edges.append({"source": cust_id, "target": rid, "label": "Rebooking option"})

        for comm in record["comms"]:
            cid = f"comm-{comm['channel']}-{comm['sent_at']}"
            channel = comm["channel"]
            time = friendly_time(comm["sent_at"])
            nodes.append(
                {
                    "id": cid,
                    "type": "Communication",
                    "label": f"Sent via {channel}",
                    "sublabel": time,
                }
            )
            edges.append({"source": cust_id, "target": cid, "label": "Notified"})

        # Baggage -> FlightOperation (CHECKED_ON) edges
        for link in record["bag_flights"]:
            if link["bag_tag"] and link["flight_num"]:
                edges.append(
                    {
                        "source": f"baggage-{link['bag_tag']}",
                        "target": f"flight-{link['flight_num']}",
                        "label": "Checked on",
                    }
                )

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
        "Booked flight",
        "Checked bag",
        "Rebooking option",
        "Notified",
        "Checked on",
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
            if "volcanic" in sublabel:
                mapping["volcanic"] = nid
                mapping["volcano"] = nid
                mapping["ash"] = nid

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

    return mapping
