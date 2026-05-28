"""Neo4j knowledge graph integration for proactive customer context.

Provides graph seeding with mock CommBank account/fraud data and
async context retrieval for use at call connection time.
"""

import asyncio
import json
import re
from typing import Dict, List, Optional

from loguru import logger


def seed_graph(driver):
    """Populate Neo4j with mock CommBank account/fraud scenario data.

    Idempotent — uses MERGE to avoid duplicates. Safe to call on every startup.

    Args:
        driver: Neo4j driver instance.
    """
    with driver.session() as session:
        session.run(
            """
            // ── Customer ──────────────────────────────────────────────────
            MERGE (c:Customer {customer_id: 'CUST-10042'})
            SET c.name = 'Jack Smith',
                c.phone = '+61412345678',
                c.tier = 'Premier'

            // ── Channel hubs ───────────────────────────────────────────────
            MERGE (ch1:Channel {name: 'Accounts'})
            SET ch1.display_name = 'Accounts Channel'

            MERGE (ch2:Channel {name: 'Cards'})
            SET ch2.display_name = 'Cards Channel'

            MERGE (ch3:Channel {name: 'Communications'})
            SET ch3.display_name = 'Communications Channel'

            MERGE (ch4:Channel {name: 'Transactions'})
            SET ch4.display_name = 'Transactions Channel'

            // ── Accounts sub-nodes: Visa card and Home Loan ────────────────
            MERGE (visa:Card {card_number: '**** **** **** 1234'})
            SET visa.card_type = 'Visa Platinum',
                visa.status = 'ACTIVE',
                visa.daily_limit = 10000,
                visa.current_balance = 4500.00

            MERGE (homeloan:HomeLoan {account_number: '200456789'})
            SET homeloan.status = 'ACTIVE',
                homeloan.next_payment = 2895.00,
                homeloan.payment_due = '2026-05-30',
                homeloan.payment_status = 'REJECTED'

            // ── Cards sub-nodes: Digital and Physical replacement cards ─────
            MERGE (digital:DigitalCard {card_id: 'DIGITAL-789456'})
            SET digital.status = 'PENDING_ACTIVATION',
                digital.issue_date = '2026-05-28',
                digital.expiry = '2029-05-28'

            MERGE (physical:PhysicalCard {card_id: 'PHYSICAL-123789'})
            SET physical.status = 'ORDERED',
                physical.issue_date = '2026-05-28',
                physical.delivery_eta = '1-2 business days',
                physical.tracking_number = 'AUSTPOST-987654321'

            // ── Communications sub-nodes ───────────────────────────────────
            MERGE (comm1:Communication {channel: 'Push Notification', sent_at: '2026-05-28T10:15:00'})
            SET comm1.message = 'Suspicious transaction detected on your Visa card - London merchant'

            MERGE (comm2:Communication {channel: 'SMS', sent_at: '2026-05-28T10:16:00'})
            SET comm2.message = 'Card temporarily frozen for security. Call 13 2221 for assistance.'

            // ── Transactions sub-nodes ────────────────────────────────────
            MERGE (t1:Transaction {id: 'TXN-LONDON-98765'})
            SET t1.amount = 850.00,
                t1.currency = 'GBP',
                t1.merchant = 'London Electronics Ltd',
                t1.location = 'London, UK',
                t1.timestamp = '2026-05-28T10:10:00',
                t1.status = 'FLAGGED',
                t1.risk_score = 0.92,
                t1.category = 'Electronics'

            // ── Channel membership ─────────────────────────────────────────
            MERGE (c)-[:HAS_CHANNEL {source: 'CommBank Core Banking'}]->(ch1)
            MERGE (c)-[:HAS_CHANNEL {source: 'CommBank Cards Platform'}]->(ch2)
            MERGE (c)-[:HAS_CHANNEL {source: 'CommBank Digital Messaging'}]->(ch3)
            MERGE (c)-[:HAS_CHANNEL {source: 'CommBank Transaction Monitoring'}]->(ch4)

            MERGE (ch1)-[:CONTAINS]->(visa)
            MERGE (ch1)-[:CONTAINS]->(homeloan)

            MERGE (ch2)-[:CONTAINS]->(digital)
            MERGE (ch2)-[:CONTAINS]->(physical)

            MERGE (ch3)-[:CONTAINS]->(comm1)
            MERGE (ch3)-[:CONTAINS]->(comm2)

            MERGE (ch4)-[:CONTAINS]->(t1)

            // ── Event chain (temporal provenance — direct from Customer) ───
            MERGE (e1:Event {id: 'evt-001'})
            SET e1.type = 'SUSPICIOUS_TRANSACTION',
                e1.timestamp = '2026-05-28T10:10:00',
                e1.description = 'GBP 850.00 transaction at London Electronics Ltd flagged as high risk'

            MERGE (e2:Event {id: 'evt-002'})
            SET e2.type = 'CARD_FROZEN',
                e2.timestamp = '2026-05-28T10:12:00',
                e2.description = 'Visa card temporarily frozen due to suspicious activity'

            MERGE (e3:Event {id: 'evt-003'})
            SET e3.type = 'PAYMENT_REJECTED',
                e3.timestamp = '2026-05-28T10:14:00',
                e1.description = 'Home loan payment rejected due to frozen card'

            MERGE (e1)-[:TRIGGERED]->(e2)
            MERGE (e2)-[:TRIGGERED]->(e3)
            MERGE (c)-[:EXPERIENCED]->(e1)
            MERGE (t1)-[:TRIGGERED]->(e1)

            // ── CallContext (call-readiness brief) ─────────────────────────
            MERGE (ctx:CallContext {customer_id: 'CUST-10042'})
            SET ctx.primary_issue = 'Visa card frozen due to suspicious GBP 850 transaction in London',
                ctx.recommended_action = 'Verify transaction with customer, offer grace period on mortgage, replace card',
                ctx.tier_flag = 'Premier — priority handling, proactive fraud detection enabled',
                ctx.card_status = 'Visa Platinum frozen, digital replacement pending, physical card ordered',
                ctx.urgency = 'HIGH'

            MERGE (c)-[:HAS_CALL_CONTEXT]->(ctx)
            """
        )
    logger.info(
        "Neo4j graph seeded with Jack Smith / CommBank Premier account context graph"
    )


def _query_customer_context_sync(driver, customer_id: str) -> Optional[str]:
    """Synchronous graph query — called via asyncio.to_thread.

    Args:
        driver: Neo4j driver instance.
        customer_id: Customer ID to look up.

    Returns:
        Formatted situation summary string, or None if customer not found.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer {customer_id: $ref})
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'Accounts'})-[:CONTAINS]->(a)
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'Cards'})-[:CONTAINS]->(card)
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'Communications'})-[:CONTAINS]->(comm:Communication)
            OPTIONAL MATCH (c)-[:HAS_CHANNEL]->(:Channel {name: 'Transactions'})-[:CONTAINS]->(txn:Transaction)
            OPTIONAL MATCH (c)-[:HAS_CALL_CONTEXT]->(ctx:CallContext)
            RETURN c,
                   collect(DISTINCT a) AS accounts,
                   collect(DISTINCT card) AS cards,
                   collect(DISTINCT comm) AS communications,
                   collect(DISTINCT txn) AS transactions,
                   ctx
            """,
            ref=customer_id,
        )

        record = result.single()
        if not record or record["c"] is None:
            return None

        customer = record["c"]
        accounts = record["accounts"]
        cards = record["cards"]
        communications = record["communications"]
        transactions = record["transactions"]

        lines = []

        # CallContext pre-assembled brief (call-readiness layer)
        ctx = record.get("ctx")
        if ctx:
            lines.append("=== PRE-CALL BRIEF (Context Graph) ===")
            lines.append("")
            lines.append(f"Primary issue:       {ctx['primary_issue']}")
            lines.append(f"Recommended action:  {ctx['recommended_action']}")
            lines.append(f"Tier flag:           {ctx['tier_flag']}")
            lines.append(f"Card status:         {ctx['card_status']}")
            lines.append(f"Urgency:             {ctx['urgency']}")
            lines.append("")

        lines.append("=== CUSTOMER SITUATION SUMMARY ===")
        lines.append("")
        lines.append(
            f"Customer: {customer['name']}, "
            f"ID: {customer['customer_id']}, "
            f"Tier: {customer['tier']}, "
            f"Phone: {customer['phone']}"
        )

        if accounts:
            lines.append("")
            lines.append("ACCOUNTS:")
            for a in accounts:
                acc_type = a.get("card_type") or a.get("account_type") or type(a).__name__
                status = a.get("status") or "ACTIVE"
                if "HomeLoan" in a.labels:
                    payment_status = a.get("payment_status", "OK")
                    next_payment = a.get("next_payment", "N/A")
                    due_date = a.get("payment_due", "N/A")
                    lines.append(
                        f"  - Home Loan: {a.get('account_number', 'N/A')} | "
                        f"Status: {status} | Payment: ${next_payment} due {due_date} | "
                        f"Last payment: {payment_status}"
                    )
                elif "Card" in a.labels and "Digital" not in a.labels and "Physical" not in a.labels:
                    balance = a.get("current_balance", "N/A")
                    daily_limit = a.get("daily_limit", "N/A")
                    lines.append(
                        f"  - {acc_type}: {a.get('card_number', 'N/A')} | "
                        f"Status: {status} | Balance: ${balance} | Daily limit: ${daily_limit}"
                    )

        if cards:
            lines.append("")
            lines.append("CARD REPLACEMENTS:")
            for card in cards:
                if "DigitalCard" in card.labels:
                    status = card.get("status", "UNKNOWN")
                    issue_date = card.get("issue_date", "N/A")
                    lines.append(
                        f"  - Digital Card: {card.get('card_id', 'N/A')} | "
                        f"Status: {status} | Issued: {issue_date}"
                    )
                elif "PhysicalCard" in card.labels:
                    status = card.get("status", "UNKNOWN")
                    eta = card.get("delivery_eta", "N/A")
                    tracking = card.get("tracking_number", "N/A")
                    lines.append(
                        f"  - Physical Card: {card.get('card_id', 'N/A')} | "
                        f"Status: {status} | ETA: {eta} | Tracking: {tracking}"
                    )

        if transactions:
            lines.append("")
            lines.append("SUSPICIOUS TRANSACTIONS:")
            for t in transactions:
                amount = t.get("amount", 0)
                currency = t.get("currency", "AUD")
                merchant = t.get("merchant", "Unknown")
                location = t.get("location", "Unknown")
                timestamp = t.get("timestamp", "Unknown")
                risk = t.get("risk_score", 0)
                status = t.get("status", "UNKNOWN")
                lines.append(
                    f"  - {currency} {amount:.2f} at {merchant} ({location}) | "
                    f"Time: {timestamp} | Risk: {risk:.2f} | Status: {status}"
                )

        if communications:
            lines.append("")
            lines.append("PRIOR COMMUNICATIONS SENT:")
            for comm in communications:
                lines.append(f"  - {comm['channel']} at {comm['sent_at']}: {comm['message']}")

        return "\n".join(lines)


async def query_customer_context(driver, customer_id: str) -> Optional[str]:
    """Query Neo4j for full customer context, async-safe.

    Args:
        driver: Neo4j driver instance.
        customer_id: Customer ID to look up.

    Returns:
        Formatted situation summary string, or None if customer not found.
    """
    return await asyncio.to_thread(_query_customer_context_sync, driver, customer_id)


def _query_customer_by_name_sync(driver, customer_name: str) -> Optional[str]:
    """Find a customer ID by customer name.

    Args:
        driver: Neo4j driver instance.
        customer_name: Full or partial customer name (case-insensitive).

    Returns:
        Customer ID string, or None if not found.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer)
            WHERE toLower(c.name) CONTAINS toLower($name)
            RETURN c.customer_id AS customer_id
            LIMIT 1
            """,
            name=customer_name.strip(),
        )
        record = result.single()
        if record and record["customer_id"]:
            return record["customer_id"]
        return None


async def query_customer_by_name(driver, customer_name: str) -> Optional[str]:
    """Find customer ID by customer name, async-safe.

    Args:
        driver: Neo4j driver instance.
        customer_name: Full or partial customer name.

    Returns:
        Customer ID string, or None if not found.
    """
    return await asyncio.to_thread(_query_customer_by_name_sync, driver, customer_name)


def _query_graph_structure_sync(driver, customer_id: str) -> Optional[Dict]:
    """Query Neo4j and return graph structure as nodes + edges for visualization.

    Args:
        driver: Neo4j driver instance.
        customer_id: Customer ID to look up.

    Returns:
        Dict with "nodes" and "edges" lists, or None if customer not found.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer {customer_id: $ref})
            OPTIONAL MATCH (c)-[hch:HAS_CHANNEL]->(ch:Channel)
            OPTIONAL MATCH (ch)-[:CONTAINS]->(sub)
            OPTIONAL MATCH (c)-[:EXPERIENCED]->(e1:Event)
            OPTIONAL MATCH (e1)-[:TRIGGERED*0..5]->(echain:Event)
            RETURN c,
                   collect(DISTINCT {ch: ch, source: hch.source}) AS channels,
                   collect(DISTINCT {ch_name: ch.name, sub: sub, sub_labels: labels(sub)}) AS sub_nodes,
                   collect(DISTINCT echain) AS events
            """,
            ref=customer_id,
        )

        record = result.single()
        if not record or record["c"] is None:
            return None

        customer = record["c"]
        nodes: List[Dict] = []
        edges: List[Dict] = []

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

        cust_id = f"customer-{customer['customer_id']}"
        nodes.append({
            "id": cust_id,
            "type": "Customer",
            "label": customer["name"],
            "sublabel": (
                f"ID: {customer['customer_id']} "
                f"· {customer['tier']} member"
            ),
        })

        # Channel hub nodes
        channel_order = ["Accounts", "Cards", "Communications", "Transactions"]
        channel_source_map = {
            "Accounts": "CommBank Core Banking",
            "Cards": "CommBank Cards Platform",
            "Communications": "CommBank Digital Messaging",
            "Transactions": "CommBank Transaction Monitoring",
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
        seen_sub: set = set()

        # Sort sub-nodes so primary account info comes first
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
            node_type = next((lbl for lbl in sub_labels if lbl != "Customer"), None)
            if node_type is None:
                continue

            ch_id = f"channel-{ch_name.lower().replace(' ', '-')}"

            if node_type == "Card":
                nid = f"card-{sub.get('card_number', 'unknown').replace(' ', '_')}"
                if nid in seen_sub:
                    continue
                seen_sub.add(nid)
                card_type = sub.get("card_type", "Unknown")
                status = sub.get("status", "ACTIVE")
                balance = sub.get("current_balance", 0)
                nodes.append({
                    "id": nid,
                    "type": "Card",
                    "label": f"{card_type}",
                    "sublabel": f"{sub.get('card_number', 'N/A')} · Status: {status} · Balance: ${balance:.2f}",
                    "alert": status != "ACTIVE",
                })
                edges.append({"source": ch_id, "target": nid, "label": "CONTAINS"})

            elif node_type == "HomeLoan":
                nid = f"homeloan-{sub.get('account_number', 'unknown')}"
                if nid in seen_sub:
                    continue
                seen_sub.add(nid)
                status = sub.get("status", "ACTIVE")
                payment = sub.get("next_payment", 0)
                due = sub.get("payment_due", "N/A")
                payment_status = sub.get("payment_status", "OK")
                status_color = "red" if payment_status == "REJECTED" else "green"
                nodes.append({
                    "id": nid,
                    "type": "HomeLoan",
                    "label": f"Home Loan {sub.get('account_number', '')}",
                    "sublabel": f"Payment: ${payment:.2f} due {due} · Status: {payment_status}",
                    "alert": payment_status == "REJECTED",
                })
                edges.append({"source": ch_id, "target": nid, "label": "CONTAINS"})

            elif node_type == "DigitalCard":
                nid = f"digitalcard-{sub.get('card_id', 'unknown')}"
                if nid in seen_sub:
                    continue
                seen_sub.add(nid)
                status = sub.get("status", "UNKNOWN")
                issue_date = sub.get("issue_date", "N/A")
                nodes.append({
                    "id": nid,
                    "type": "DigitalCard",
                    "label": "Digital Card",
                    "sublabel": f"ID: {sub.get('card_id', 'N/A')} · Status: {status} · Issued: {issue_date}",
                })
                edges.append({"source": ch_id, "target": nid, "label": "CONTAINS"})

            elif node_type == "PhysicalCard":
                nid = f"physicalcard-{sub.get('card_id', 'unknown')}"
                if nid in seen_sub:
                    continue
                seen_sub.add(nid)
                status = sub.get("status", "UNKNOWN")
                eta = sub.get("delivery_eta", "N/A")
                nodes.append({
                    "id": nid,
                    "type": "PhysicalCard",
                    "label": "Physical Card",
                    "sublabel": f"ETA: {eta} · Status: {status}",
                })
                edges.append({"source": ch_id, "target": nid, "label": "CONTAINS"})

            elif node_type == "Communication":
                cid = f"comm-{sub['channel'].lower().replace(' ', '_')}-{sub.get('sent_at', '0').replace(':', '')}"
                if cid in seen_sub:
                    continue
                seen_sub.add(cid)
                time_str = friendly_time(sub["sent_at"])
                nodes.append({
                    "id": cid,
                    "type": "Communication",
                    "label": f"{sub['channel']}",
                    "sublabel": f"{time_str} · {sub['message']}",
                })
                edges.append({"source": ch_id, "target": cid, "label": "CONTAINS"})

            elif node_type == "Transaction":
                tid = f"txn-{sub.get('id', 'unknown')}"
                if tid in seen_sub:
                    continue
                seen_sub.add(tid)
                amount = sub.get("amount", 0)
                currency = sub.get("currency", "AUD")
                merchant = sub.get("merchant", "Unknown")
                location = sub.get("location", "Unknown")
                status = sub.get("status", "UNKNOWN")
                nodes.append({
                    "id": tid,
                    "type": "Transaction",
                    "label": f"{currency} {amount:.2f}",
                    "sublabel": f"{merchant} ({location}) · {status} · Risk: {sub.get('risk_score', 0):.2f}",
                    "alert": status == "FLAGGED",
                })
                edges.append({"source": ch_id, "target": tid, "label": "CONTAINS"})

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


async def query_graph_structure(driver, customer_id: str) -> Optional[Dict]:
    """Query Neo4j for graph structure (nodes + edges), async-safe.

    Args:
        driver: Neo4j driver instance.
        customer_id: Customer ID to look up.

    Returns:
        Dict with "nodes" and "edges" lists, or None if customer not found.
    """
    return await asyncio.to_thread(_query_graph_structure_sync, driver, customer_id)


def build_traversal_sequence(graph: Dict) -> List[Dict]:
    """Build an ordered traversal sequence for animating graph exploration.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.

    Returns:
        List of event dicts for the frontend to animate.
    """
    if not graph:
        return []

    events: List[Dict] = []
    node_ids = {n["id"] for n in graph["nodes"]}

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
        "CommBank Core Banking",
        "CommBank Cards Platform",
        "CommBank Digital Messaging",
        "CommBank Transaction Monitoring",
        "CONTAINS",
        "Experienced",
        "Triggered",
    ]

    edge_by_label: Dict[str, List[Dict]] = {}
    for e in graph["edges"]:
        edge_by_label.setdefault(e["label"], []).append(e)

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
            continue

        elif ntype == "Customer":
            name = node.get("label", "")
            if name:
                mapping[name.lower()] = nid
                first = name.split()[0].lower()
                if len(first) > 2:
                    mapping[first] = nid

        elif ntype == "Card":
            label = node.get("label", "").lower()
            sublabel = node.get("sublabel", "").lower()
            mapping["visa"] = nid
            mapping["card"] = nid
            if "platinum" in label or "platinum" in sublabel:
                mapping["platinum"] = nid
            if "frozen" in sublabel:
                mapping["frozen"] = nid
                mapping["blocked"] = nid
            if "limit" in sublabel:
                mapping["limit"] = nid
                mapping["daily limit"] = nid

        elif ntype == "HomeLoan":
            label = node.get("label", "").lower()
            sublabel = node.get("sublabel", "").lower()
            mapping["home loan"] = nid
            mapping["mortgage"] = nid
            if "rejected" in sublabel:
                mapping["rejected"] = nid
                mapping["payment failed"] = nid
                mapping["payment"] = nid

        elif ntype == "DigitalCard":
            mapping["digital card"] = nid
            mapping["digital"] = nid
            if "active" in node.get("sublabel", "").lower():
                mapping["activated"] = nid

        elif ntype == "PhysicalCard":
            mapping["physical card"] = nid
            mapping["new card"] = nid
            mapping["replacement"] = nid
            if "eta" in node.get("sublabel", "").lower():
                mapping["eta"] = nid
                mapping["delivery"] = nid

        elif ntype == "Communication":
            label = node.get("label", "").lower()
            sublabel = node.get("sublabel", "").lower()
            if "push" in label:
                mapping["push"] = nid
                mapping["notification"] = nid
                mapping["app"] = nid
            elif "sms" in label:
                mapping["sms"] = nid
                mapping["text"] = nid
                mapping["message"] = nid
            if "london" in sublabel:
                mapping["london"] = nid
                mapping["uk"] = nid
            if "suspicious" in sublabel or "fraud" in sublabel:
                mapping["suspicious"] = nid
                mapping["fraud"] = nid
                mapping["security"] = nid

        elif ntype == "Transaction":
            label = node.get("label", "").lower()
            sublabel = node.get("sublabel", "").lower()
            # Extract amount and merchant
            if "gbp" in label or "pound" in label:
                mapping["gbp"] = nid
                mapping["pounds"] = nid
            if "850" in label:
                mapping["850"] = nid
                mapping["eight hundred fifty"] = nid
            if "london" in sublabel:
                mapping["london"] = nid
            if "electronics" in sublabel:
                mapping["electronics"] = nid
                mapping["purchase"] = nid
            if "flagged" in sublabel or "high risk" in sublabel:
                mapping["flagged"] = nid
                mapping["high risk"] = nid

        elif ntype == "Event":
            label = node.get("label", "").lower()
            sublabel = node.get("sublabel", "").lower()
            if "suspicious" in label or "transaction" in label:
                mapping["transaction"] = nid
                mapping["suspicious"] = nid
            if "frozen" in label or "frozen" in sublabel:
                mapping["frozen"] = nid
                mapping["freeze"] = nid
            if "payment" in label and "rejected" in label:
                mapping["rejected"] = nid
            if "grace" in sublabel:
                mapping["grace"] = nid
                mapping["period"] = nid

    return mapping


def build_path_map(graph: Dict) -> Dict[str, Dict]:
    """Build channel path definitions for sequential graph traversal animation.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.

    Returns:
        Dict mapping lowercase keyword/phrase to
        ``{"steps": [nodeId, ...], "color": "#hex"}``.
    """
    if not graph:
        return {}

    CHANNEL_COLORS = {
        "accounts": "#fbbf24",
        "cards": "#f97316",
        "communications": "#10b981",
        "transactions": "#8b5cf6",
    }

    CHANNEL_KEYWORDS: Dict[str, List[str]] = {
        "accounts": [
            "account", "accounts", "home loan", "mortgage", "payment",
            "loan", "balance",
        ],
        "cards": [
            "card", "cards", "visa", "digital card", "physical card",
            "replacement", "new card",
        ],
        "communications": [
            "communication", "notification", "notified", "push", "sms",
            "message", "app", "text",
        ],
        "transactions": [
            "transaction", "purchase", "merchant", "amount",
            "suspicious", "fraud", "london",
        ],
    }

    node_map = {n["id"]: n for n in graph["nodes"]}

    customer_id = next(
        (n["id"] for n in graph["nodes"] if n["type"] == "Customer"), None
    )
    if not customer_id:
        return {}

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


def _query_transaction_context_sync(driver, customer_id: str) -> Optional[Dict]:
    """Query transactions for a customer.

    Args:
        driver: Neo4j driver instance.
        customer_id: Customer ID.

    Returns:
        Dict with "summary" and "node_ids", or None if not found.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer {customer_id: $ref})
                  -[:HAS_CHANNEL]->(:Channel {name: 'Transactions'})
                  -[:CONTAINS]->(t:Transaction)
            RETURN collect(t) AS transactions
            """,
            ref=customer_id,
        )
        record = result.single()
        if not record or not record["transactions"]:
            return None

        txns = record["transactions"]
        lines = [f"{len(txns)} flagged transaction(s):"]
        node_ids = []
        for i, t in enumerate(txns, 1):
            amount = t.get("amount", 0)
            currency = t.get("currency", "AUD")
            merchant = t.get("merchant", "Unknown")
            location = t.get("location", "Unknown")
            timestamp = t.get("timestamp", "Unknown")
            risk = t.get("risk_score", 0)
            status = t.get("status", "UNKNOWN")
            lines.append(
                f"  Transaction {i}: {currency} {amount:.2f} at {merchant} ({location}) | "
                f"Time: {timestamp} | Risk Score: {risk:.2f} | Status: {status}"
            )
            node_ids.append(f"txn-{t.get('id', 'unknown')}")

        return {"summary": "\n".join(lines), "node_ids": node_ids}


async def query_transaction_context(driver, customer_id: str) -> Optional[Dict]:
    """Query transaction context for a customer, async-safe.

    Args:
        driver: Neo4j driver instance.
        customer_id: Customer ID.

    Returns:
        Dict with "summary" and "node_ids", or None if not found.
    """
    return await asyncio.to_thread(_query_transaction_context_sync, driver, customer_id)
