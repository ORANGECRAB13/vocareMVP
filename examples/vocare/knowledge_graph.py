"""Neo4j knowledge graph integration for Georges River Council (GRC) voice agent.

Provides graph seeding with GRC service structure and bin zone geodata,
async bin zone lookup via point-in-polygon, and graph visualization support.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


_DAY_MAP = {
    "mon": "Monday",
    "tues": "Tuesday",
    "wed": "Wednesday",
    "thurs": "Thursday",
    "fri": "Friday",
}

_ZONES_DIR = Path(__file__).parent / "GRC_pilot" / "api" / "zones"

# Channel display order
_CHANNEL_ORDER = ["Bin Collection", "Bulky Waste", "Development Applications"]

# ---------------------------------------------------------------------------
# Suburb-level bin day cache
# Coordinates verified by point-in-polygon check against GRC geojson zones.
# ---------------------------------------------------------------------------

# Representative interior points (lat, lng) for each GRC suburb.
# Using zone centroid proxies where suburb centroid lies on a zone edge.
_SUBURB_SAMPLE_POINTS: Dict[str, tuple] = {
    "beverly hills":    (-33.953,  151.074),
    "narwee":           (-33.952,  151.062),
    "riverwood":        (-33.950,  151.070),
    "kingsgrove":       (-33.947,  151.093),
    "bexley":           (-33.955,  151.103),
    "bexley north":     (-33.945,  151.102),
    "penshurst":        (-33.967,  151.076),
    "hurstville":       (-33.969,  151.097),
    "south hurstville": (-33.977,  151.099),
    "hurstville grove": (-33.978,  151.105),
    "mortdale":         (-33.977,  151.082),
    "blakehurst":       (-33.990,  151.104),
    "carss park":       (-33.993,  151.112),
    "connells point":   (-33.987,  151.103),   # thurs_zone2 centroid proxy
    "kyle bay":         (-33.987,  151.103),   # thurs_zone2 centroid proxy
    "kogarah":          (-33.972,  151.112),   # wed_zone1 centroid proxy
    "kogarah bay":      (-33.972,  151.128),
    "carlton":          (-33.962,  151.112),
    "allawah":          (-33.972,  151.112),   # wed_zone1 centroid proxy
    "monterey":         (-33.974,  151.135),
    "ramsgate":         (-33.980,  151.130),
    "ramsgate beach":   (-33.984,  151.136),
    "sans souci":       (-33.981,  151.128),   # wed_zone2 centroid proxy
    "dolls point":      (-33.981,  151.128),   # wed_zone2 centroid proxy
    "sandringham":      (-33.981,  151.128),   # wed_zone2 centroid proxy
    "peakhurst":        (-33.988,  151.075),
    "lugarno":          (-33.982,  151.047),   # fri_zone1 centroid proxy
    "oatley":           (-33.978,  151.067),   # fri_zone2 centroid proxy
}

# Built once at module load (no Neo4j required — reads geojson files directly)
_SUBURB_DAY_CACHE: Optional[Dict[str, str]] = None


def _load_all_zone_rings() -> list:
    """Load all geojson zone files and return [(zone_id, day, [rings])] list."""
    result = []
    for path in sorted(_ZONES_DIR.glob("*.geojson")):
        m = re.match(r"^([a-z]+)_zone(\d+)$", path.stem)
        if not m:
            continue
        day = _DAY_MAP.get(m.group(1))
        if not day:
            continue
        with open(path) as f:
            gj = json.load(f)
        rings = [feat["geometry"]["coordinates"][0] for feat in gj["features"]]
        result.append((path.stem, day, rings))
    return result


def _build_suburb_day_cache() -> Dict[str, str]:
    """Compute suburb → collection day by running PIP against geojson files.

    Returns:
        Dict mapping lowercase suburb name to day string, e.g. {"hurstville": "Thursday"}.
    """
    zones = _load_all_zone_rings()
    cache: Dict[str, str] = {}
    for suburb, (lat, lng) in _SUBURB_SAMPLE_POINTS.items():
        for _zone_id, day, rings in zones:
            for ring in rings:
                if _point_in_polygon_raycast(lat, lng, ring):
                    cache[suburb] = day
                    break
            if suburb in cache:
                break
    logger.info(f"Suburb cache built: {len(cache)}/{len(_SUBURB_SAMPLE_POINTS)} suburbs mapped")
    return cache


def get_suburb_day_cache() -> Dict[str, str]:
    """Return the suburb → collection day cache, building it on first call.

    Returns:
        Dict mapping lowercase suburb name to day string.
    """
    global _SUBURB_DAY_CACHE
    if _SUBURB_DAY_CACHE is None:
        _SUBURB_DAY_CACHE = _build_suburb_day_cache()
    return _SUBURB_DAY_CACHE


def format_bin_days_for_prompt() -> str:
    """Format the suburb cache as a prompt-injectable lookup table.

    Returns:
        Multiline string grouping suburbs by collection day.
    """
    from collections import defaultdict

    cache = get_suburb_day_cache()
    by_day: dict = defaultdict(list)
    for suburb, day in sorted(cache.items()):
        by_day[day].append(suburb.title())

    lines = ["BIN COLLECTION DAYS BY SUBURB (Georges River LGA):"]
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        if by_day[day]:
            lines.append(f"  {day}: {', '.join(sorted(by_day[day]))}")
    return "\n".join(lines)


def lookup_bin_day_by_address(address: str) -> Optional[str]:
    """Extract suburb from a free-text address and look up bin collection day.

    Args:
        address: Full or partial address string.

    Returns:
        Collection day string (e.g. "Thursday") or None if suburb not found.
    """
    cache = get_suburb_day_cache()
    address_lower = address.lower()
    # Match longest suburb name first to avoid partial matches
    for suburb in sorted(cache.keys(), key=len, reverse=True):
        if suburb in address_lower:
            return cache[suburb]
    return None


def seed_graph(driver):
    """Populate Neo4j with GRC service structure and bin zone geodata.

    Idempotent — uses MERGE to avoid duplicates. Safe to call on every startup.

    Args:
        driver: Neo4j driver instance.
    """
    with driver.session() as session:
        session.run(
            """
            MERGE (ca:CouncilArea {name: 'Georges River Council'})
            SET ca.lga = 'Georges River', ca.state = 'NSW'

            MERGE (ch1:Channel {name: 'Bin Collection'})
            SET ch1.display_name = 'Bin Collection'

            MERGE (ch2:Channel {name: 'Bulky Waste'})
            SET ch2.display_name = 'Bulky Waste Collection'

            MERGE (ch3:Channel {name: 'Development Applications'})
            SET ch3.display_name = 'Development Applications'

            MERGE (ca)-[:HAS_CHANNEL]->(ch1)
            MERGE (ca)-[:HAS_CHANNEL]->(ch2)
            MERGE (ca)-[:HAS_CHANNEL]->(ch3)

            MERGE (si1:ServiceInfo {name: 'Bulky Waste Collection'})
            SET si1.entitlements = 2, si1.booking_lead_days = 14

            MERGE (si2:ServiceInfo {name: 'Development Applications'})
            SET si2.lodge_via = 'NSW Planning Portal'

            MERGE (ch2)-[:CONTAINS]->(si1)
            MERGE (ch3)-[:CONTAINS]->(si2)
            """
        )

        # Load BinZone nodes from geojson files
        for geojson_path in sorted(_ZONES_DIR.glob("*.geojson")):
            stem = geojson_path.stem  # e.g. "mon_zone1"
            match = re.match(r"^([a-z]+)_zone(\d+)$", stem)
            if not match:
                logger.warning(f"Skipping unrecognised zone file: {geojson_path.name}")
                continue

            day_abbr = match.group(1)
            zone_number = int(match.group(2))
            day = _DAY_MAP.get(day_abbr)
            if not day:
                logger.warning(f"Unknown day abbreviation '{day_abbr}' in {geojson_path.name}")
                continue

            with open(geojson_path) as f:
                geojson = json.load(f)

            # Collect all coordinate rings across all features (handles multi-polygon files)
            all_rings = [
                feat["geometry"]["coordinates"][0]
                for feat in geojson["features"]
            ]
            polygon_json = json.dumps(all_rings)
            zone_id = f"{day_abbr}_zone_{zone_number}"

            session.run(
                """
                MATCH (ch:Channel {name: 'Bin Collection'})
                MERGE (bz:BinZone {zone_id: $zone_id})
                SET bz.day = $day,
                    bz.zone_number = $zone_number,
                    bz.polygon_json = $polygon_json
                MERGE (ch)-[:CONTAINS]->(bz)
                """,
                zone_id=zone_id,
                day=day,
                zone_number=zone_number,
                polygon_json=polygon_json,
            )

    logger.info("GRC graph seeded: CouncilArea → 3 Channels → 10 BinZones + 2 ServiceInfo nodes")


# ---------------------------------------------------------------------------
# Point-in-polygon helpers
# ---------------------------------------------------------------------------


def _point_in_polygon_shapely(lat: float, lng: float, coords) -> bool:
    """Check point-in-polygon using shapely (lng, lat = x, y)."""
    from shapely.geometry import Point, Polygon

    return Polygon(coords).contains(Point(lng, lat))


def _point_in_polygon_raycast(lat: float, lng: float, coords) -> bool:
    """Pure Python ray-casting fallback for point-in-polygon."""
    x, y = lng, lat
    n = len(coords)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = coords[i][0], coords[i][1]
        xj, yj = coords[j][0], coords[j][1]
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _query_bin_zone_for_point_sync(driver, lat: float, lng: float) -> Optional[Dict]:
    """Fetch all BinZone polygons from Neo4j and run point-in-polygon check.

    Args:
        driver: Neo4j driver instance.
        lat: Latitude of the address point.
        lng: Longitude of the address point.

    Returns:
        Dict with zone_id, day, and voice_prompt, or None if no zone matched.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (bz:BinZone)
            RETURN bz.zone_id AS zone_id, bz.day AS day,
                   bz.zone_number AS zone_number, bz.polygon_json AS polygon_json
            ORDER BY bz.day, bz.zone_number
            """
        )
        zones = list(result)

    try:
        import shapely  # noqa: F401
        pip_fn = _point_in_polygon_shapely
    except ImportError:
        logger.debug("shapely not available — using ray-casting for point-in-polygon")
        pip_fn = _point_in_polygon_raycast

    for record in zones:
        try:
            rings = json.loads(record["polygon_json"])
            # polygon_json is now a list of rings (handles multi-polygon zones)
            for ring in rings:
                if pip_fn(lat, lng, ring):
                    day = record["day"]
                    return {
                        "zone_id": record["zone_id"],
                        "day": day,
                        "voice_prompt": f"Your bins are collected every {day}.",
                    }
        except Exception as e:
            logger.warning(f"Point-in-polygon failed for {record['zone_id']}: {e}")

    return None


async def query_bin_zone_for_point(driver, lat: float, lng: float) -> Optional[Dict]:
    """Find the bin collection zone for a lat/lng point, async-safe.

    Args:
        driver: Neo4j driver instance.
        lat: Latitude of the address point.
        lng: Longitude of the address point.

    Returns:
        Dict with zone_id, day, and voice_prompt, or None if not found.
    """
    return await asyncio.to_thread(_query_bin_zone_for_point_sync, driver, lat, lng)


# ---------------------------------------------------------------------------
# Graph structure for frontend visualization
# ---------------------------------------------------------------------------


def _query_graph_structure_sync(driver) -> Dict:
    """Query Neo4j and return GRC service graph as nodes + edges.

    Args:
        driver: Neo4j driver instance.

    Returns:
        Dict with "nodes" and "edges" lists.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (ca:CouncilArea)
            OPTIONAL MATCH (ca)-[:HAS_CHANNEL]->(ch:Channel)
            OPTIONAL MATCH (ch)-[:CONTAINS]->(sub)
            RETURN ca,
                   collect(DISTINCT ch) AS channels,
                   collect(DISTINCT {ch_name: ch.name, sub: sub,
                                     sub_labels: labels(sub)}) AS sub_nodes
            """
        )
        record = result.single()

    if not record or record["ca"] is None:
        return {"nodes": [], "edges": []}

    ca = record["ca"]
    nodes: List[Dict] = []
    edges: List[Dict] = []

    ca_id = "council-grc"
    nodes.append({
        "id": ca_id,
        "type": "CouncilArea",
        "label": ca["name"],
        "sublabel": "Local Government Area · NSW",
    })

    _CHANNEL_SUBTITLES = {
        "Bin Collection": "Kerbside Services",
        "Bulky Waste": "Waste Management",
        "Development Applications": "Planning & Compliance",
    }

    seen_channels: set = set()
    sorted_channels = sorted(
        record["channels"],
        key=lambda ch: (
            _CHANNEL_ORDER.index(ch["name"]) if ch and ch["name"] in _CHANNEL_ORDER else 999
        ),
    )
    for ch in sorted_channels:
        if ch is None or ch["name"] in seen_channels:
            continue
        seen_channels.add(ch["name"])
        ch_id = f"channel-{ch['name'].lower().replace(' ', '-')}"
        nodes.append({
            "id": ch_id,
            "type": "Channel",
            "label": ch["name"],
            "sublabel": _CHANNEL_SUBTITLES.get(ch["name"], ch["name"]),
        })
        edges.append({"source": ca_id, "target": ch_id, "label": ch["name"]})

    # Sub-nodes: sort by channel order, then by type/name for determinism
    sub_items = [
        item for item in record["sub_nodes"]
        if item["sub"] is not None
    ]
    sub_items.sort(key=lambda item: (
        _CHANNEL_ORDER.index(item["ch_name"]) if item["ch_name"] in _CHANNEL_ORDER else 999
    ))

    seen_sub: set = set()
    for item in sub_items:
        sub = item["sub"]
        sub_labels = item["sub_labels"] or []
        ch_name = item["ch_name"]
        ch_id = f"channel-{ch_name.lower().replace(' ', '-')}"

        node_type = next(
            (lbl for lbl in sub_labels if lbl in {"BinZone", "ServiceInfo"}), None
        )
        if node_type is None:
            continue

        if node_type == "BinZone":
            nid = f"binzone-{sub['zone_id']}"
            if nid in seen_sub:
                continue
            seen_sub.add(nid)
            nodes.append({
                "id": nid,
                "type": "BinZone",
                "label": f"{sub['day']} Zone {sub['zone_number']}",
                "sublabel": sub["zone_id"],
            })
            edges.append({"source": ch_id, "target": nid, "label": "CONTAINS"})

        elif node_type == "ServiceInfo":
            nid = f"service-{sub['name'].lower().replace(' ', '-')}"
            if nid in seen_sub:
                continue
            seen_sub.add(nid)
            if "Bulky" in sub["name"]:
                sublabel = f"{sub.get('entitlements', 2)} collections / year"
            else:
                sublabel = f"Lodge via {sub.get('lodge_via', 'NSW Planning Portal')}"
            nodes.append({
                "id": nid,
                "type": "ServiceInfo",
                "label": sub["name"],
                "sublabel": sublabel,
            })
            edges.append({"source": ch_id, "target": nid, "label": "CONTAINS"})

    return {"nodes": nodes, "edges": edges}


async def query_graph_structure(driver) -> Dict:
    """Query Neo4j for GRC service graph structure, async-safe.

    Args:
        driver: Neo4j driver instance.

    Returns:
        Dict with "nodes" and "edges" lists.
    """
    return await asyncio.to_thread(_query_graph_structure_sync, driver)


# ---------------------------------------------------------------------------
# Animation & keyword helpers
# ---------------------------------------------------------------------------


def build_traversal_sequence(graph: Dict) -> List[Dict]:
    """Build ordered traversal for animating the GRC service graph.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.

    Returns:
        List of event dicts for the frontend to animate.
    """
    if not graph:
        return []

    council_id = next(
        (n["id"] for n in graph["nodes"] if n["type"] == "CouncilArea"), None
    )
    if not council_id:
        return []

    events: List[Dict] = [{"type": "activate", "nodeId": council_id}]

    node_map = {n["id"]: n for n in graph["nodes"]}
    channel_edges = []
    sub_edges = []

    for edge in graph["edges"]:
        src_type = node_map.get(edge["source"], {}).get("type")
        if src_type == "CouncilArea":
            channel_edges.append(edge)
        elif src_type == "Channel":
            sub_edges.append(edge)

    for edge in channel_edges:
        events.append({
            "type": "traverse",
            "fromId": edge["source"],
            "toId": edge["target"],
            "label": edge["label"],
        })

    for edge in sub_edges:
        events.append({
            "type": "traverse",
            "fromId": edge["source"],
            "toId": edge["target"],
            "label": edge["label"],
        })

    return events


def build_keyword_map(graph: Dict) -> Dict[str, str]:
    """Build keyword-to-nodeId map for GRC conversation-aware highlighting.

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

        if ntype == "CouncilArea":
            mapping["council"] = nid
            mapping["georges river"] = nid
            mapping["grc"] = nid

        elif ntype == "Channel":
            ch_name = node.get("label", "").lower()
            if "bin" in ch_name:
                mapping["bin day"] = nid
                mapping["bins"] = nid
                mapping["rubbish day"] = nid
                mapping["kerbside"] = nid
            elif "bulky" in ch_name:
                mapping["bulky"] = nid
                mapping["large items"] = nid
                mapping["furniture pickup"] = nid
            elif "development" in ch_name:
                mapping["development"] = nid
                mapping["planning"] = nid
                mapping["da inquiry"] = nid

        elif ntype == "BinZone":
            # Map each day name to the first zone for that day we encounter
            day = node.get("label", "").split()[0].lower()
            if day and day not in mapping:
                mapping[day] = nid

        elif ntype == "ServiceInfo":
            label = node.get("label", "").lower()
            if "bulky" in label:
                mapping["book a collection"] = nid
                mapping["entitlement"] = nid
                mapping["booking"] = nid
                mapping["schedule"] = nid
            elif "development" in label:
                mapping["lodge"] = nid
                mapping["application"] = nid
                mapping["approval"] = nid
                mapping["planning portal"] = nid

    return mapping


def build_path_map(graph: Dict) -> Dict[str, Dict]:
    """Build channel path definitions for sequential traversal animation.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.

    Returns:
        Dict mapping keyword/phrase to {"steps": [...], "color": "#hex"}.
    """
    if not graph:
        return {}

    CHANNEL_COLORS = {
        "bin-collection": "#10b981",
        "bulky-waste": "#f97316",
        "development-applications": "#8b5cf6",
    }

    CHANNEL_KEYWORDS: Dict[str, List[str]] = {
        "bin-collection": [
            "bin collection", "collection day", "bins collected",
            "rubbish day", "recycling day",
        ],
        "bulky-waste": [
            "bulky waste", "bulky collection", "large item",
            "book a collection", "furniture collection",
        ],
        "development-applications": [
            "development application", "planning application",
            "building approval", "complying development", "da lodgement",
        ],
    }

    node_map = {n["id"]: n for n in graph["nodes"]}
    council_id = next(
        (n["id"] for n in graph["nodes"] if n["type"] == "CouncilArea"), None
    )
    if not council_id:
        return {}

    channel_children: Dict[str, List[str]] = {}
    for edge in graph.get("edges", []):
        src_node = node_map.get(edge["source"])
        if src_node and src_node["type"] == "Channel":
            channel_children.setdefault(edge["source"], []).append(edge["target"])

    path_map: Dict[str, Dict] = {}
    for node in graph["nodes"]:
        if node["type"] != "Channel":
            continue
        ch_id = node["id"]
        ch_key = ch_id.replace("channel-", "")
        color = CHANNEL_COLORS.get(ch_key, "#64748b")
        sub_ids = channel_children.get(ch_id, [])
        path_def = {"steps": [council_id, ch_id] + sub_ids, "color": color}
        for kw in CHANNEL_KEYWORDS.get(ch_key, []):
            path_map[kw] = path_def

    return path_map


def highlight_zone_node(graph: Dict, zone_id: str) -> List[str]:
    """Return node IDs for a given bin zone ID.

    Args:
        graph: Dict with "nodes" and "edges" from query_graph_structure.
        zone_id: Zone ID string, e.g. "mon_zone_1".

    Returns:
        List of node IDs to highlight (usually just one).
    """
    nid = f"binzone-{zone_id}"
    if any(n["id"] == nid for n in graph.get("nodes", [])):
        return [nid]
    return []
