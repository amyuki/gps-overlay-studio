"""GPX parsing, enrichment, and time-index utilities."""

import bisect
import math
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two lat/lon points."""
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_gpx(path: str) -> List[dict]:
    """Parse a GPX file and return a list of track points."""
    tree = ET.parse(path)
    root = tree.getroot()
    tag = root.tag
    ns_uri = (
        tag.split("}")[0][1:]
        if tag.startswith("{")
        else "http://www.topografix.com/GPX/1/1"
    )
    ns = {"g": ns_uri}

    points = []
    for pt in root.findall(".//g:trkpt", ns):
        lat = float(pt.get("lat"))
        lon = float(pt.get("lon"))
        ele_el = pt.find("g:ele", ns)
        ele = float(ele_el.text) if ele_el is not None else 0.0
        t = None
        tel = pt.find("g:time", ns)
        if tel is not None:
            try:
                t = datetime.fromisoformat(tel.text.replace("Z", "+00:00"))
            except Exception:
                pass
        points.append({"lat": lat, "lon": lon, "ele": ele, "time": t})

    print(f"[GPX] {len(points)} track points")
    return points


def enrich_points(points: List[dict]) -> List[dict]:
    """Add speed (km/h), grade (%), and cumulative distance (km) to each point."""
    total_dist = 0.0
    for i, p in enumerate(points):
        if i == 0:
            p["speed"] = 0.0
            p["grade"] = 0.0
            p["dist"] = 0.0
            continue
        prev = points[i - 1]
        d = haversine(prev["lat"], prev["lon"], p["lat"], p["lon"])
        total_dist += d
        p["dist"] = total_dist / 1000  # km

        if prev["time"] and p["time"]:
            dt = (p["time"] - prev["time"]).total_seconds()
            p["speed"] = min((d / dt * 3.6) if dt > 0 else 0.0, 250.0)
        else:
            p["speed"] = 0.0

        ele_diff = p["ele"] - prev["ele"]
        p["grade"] = (ele_diff / d * 100) if d > 0.5 else 0.0

    points[0]["dist"] = 0.0
    return points


def make_time_index(points: List[dict]) -> Optional[List[float]]:
    """Return elapsed seconds per point; gaps are linearly interpolated so bisect works."""
    if not points[0]["time"]:
        return None
    t0 = points[0]["time"]
    raw = [
        (p["time"] - t0).total_seconds() if p["time"] else None for p in points
    ]
    out = []
    for i, v in enumerate(raw):
        if v is not None:
            out.append(v)
        else:
            prev = next((raw[j] for j in range(i - 1, -1, -1) if raw[j] is not None), 0.0)
            nxt = next((raw[j] for j in range(i + 1, len(raw)) if raw[j] is not None), prev)
            out.append((prev + nxt) / 2)
    return out


def find_idx(time_index: Optional[List[float]], video_sec: float, offset: float) -> int:
    """Binary-search the time index to find the GPX point for a given video timestamp."""
    if time_index is None:
        return 0
    t = video_sec + offset
    i = bisect.bisect_right(time_index, t) - 1
    return max(0, min(i, len(time_index) - 1))
