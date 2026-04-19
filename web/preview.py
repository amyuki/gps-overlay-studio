"""GPX preview utilities for the web UI."""

import base64

import cv2

from gps_overlay.gpx import haversine, parse_gpx, enrich_points


def clean_path(p: str) -> str:
    """Strip leading/trailing quotes and whitespace from a path string."""
    if not p:
        return ""
    return p.strip().strip('"').strip("'").strip()


def quick_parse_gpx(path: str) -> dict:
    """Parse a GPX file and return normalised preview data for the canvas UI."""
    try:
        points = parse_gpx(path)
        if len(points) < 2:
            return {"ok": False, "error": "Not enough GPX track points"}

        points = enrich_points(points)

        eles = [p["ele"] for p in points]
        lats = [p["lat"] for p in points]
        lons = [p["lon"] for p in points]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        lat_range = max(lat_max - lat_min, 1e-6)
        lon_range = max(lon_max - lon_min, 1e-6)

        step = max(1, len(points) // 300)
        track = [
            {
                "x": (p["lon"] - lon_min) / lon_range,
                "y": 1.0 - (p["lat"] - lat_min) / lat_range,
                "ele": p["ele"],
                "speed": p["speed"],
            }
            for p in points[::step]
        ]

        ele_step = max(1, len(eles) // 200)
        ele_profile = [
            {"x": i / max(len(eles) - 1, 1), "y": eles[i]}
            for i in range(0, len(eles), ele_step)
        ]

        return {
            "ok": True,
            "count": len(points),
            "has_time": points[0]["time"] is not None,
            "ele_min": min(eles),
            "ele_max": max(eles),
            "speed_max": max(p["speed"] for p in points),
            "total_km": points[-1]["dist"],
            "track": track,
            "ele_profile": ele_profile,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def extract_frame(path: str, pos: float = 0.4) -> dict:
    """Extract a single frame from a video and return it as a base64 JPEG."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"ok": False, "error": "Cannot open video"}
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if total < 1:
        cap.release()
        return {"ok": False, "error": "No frames found"}
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * pos))
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return {"ok": False, "error": "Cannot read frame"}
    h, w = frame.shape[:2]
    if w > 960:
        nh = int(h * 960 / w)
        frame = cv2.resize(frame, (960, nh))
        h, w = nh, 960
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    b64 = base64.b64encode(buf.tobytes()).decode()
    return {"ok": True, "data": f"data:image/jpeg;base64,{b64}", "w": w, "h": h}
