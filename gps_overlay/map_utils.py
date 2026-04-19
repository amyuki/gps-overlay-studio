"""Map tile fetching and canvas composition."""

import math
from typing import List, Optional, Tuple

import cv2
import numpy as np
import requests


def ll_to_tile(lat: float, lon: float, z: int) -> Tuple[int, int]:
    """Convert lat/lon to tile XY at zoom level z."""
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int(
        (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi)
        / 2 * n
    )
    return x, y


def ll_to_px(
    lat: float, lon: float, tx: int, ty: int, z: int, tile_size: int = 256
) -> Tuple[int, int]:
    """Convert lat/lon to pixel coordinates relative to tile origin (tx, ty)."""
    n = 2 ** z
    px = (lon + 180) / 360 * n * tile_size - tx * tile_size
    py = (
        (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi)
        / 2 * n * tile_size
        - ty * tile_size
    )
    return int(px), int(py)


def fetch_tile(z: int, x: int, y: int, url_tpl: str) -> Optional[np.ndarray]:
    """Download a single map tile image; returns None on failure."""
    url = url_tpl.format(z=z, x=x, y=y)
    try:
        r = requests.get(url, headers={"User-Agent": "GPSOverlayV2/1.0"}, timeout=10)
        if r.status_code == 200:
            arr = np.frombuffer(r.content, np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        pass
    return None


def build_map_canvas(
    points: List[dict], zoom: int, url_tpl: str, grid: int = 3
) -> Tuple[np.ndarray, int, int]:
    """Download a grid of map tiles centred on the track and return (canvas, tx0, ty0)."""
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    cx, cy = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
    tx, ty = ll_to_tile(cx, cy, zoom)

    half = grid // 2
    print(f"[MAP] Downloading {grid}x{grid} map tiles...")
    tiles = {}
    for dx in range(-half, half + 1):
        for dy in range(-half, half + 1):
            t = fetch_tile(zoom, tx + dx, ty + dy, url_tpl)
            if t is not None:
                tiles[(dx, dy)] = t

    if not tiles:
        blank = np.full((256 * grid, 256 * grid, 3), 30, dtype=np.uint8)
        return blank, tx - half, ty - half

    th, tw = list(tiles.values())[0].shape[:2]
    canvas = np.zeros((th * grid, tw * grid, 3), dtype=np.uint8)
    for (dx, dy), tile in tiles.items():
        x0 = (dx + half) * tw
        y0 = (dy + half) * th
        canvas[y0:y0 + th, x0:x0 + tw] = tile

    return canvas, tx - half, ty - half


def build_plain_canvas(
    points: List[dict], zoom: int, grid: int = 5, bg: Tuple[int, int, int] = (24, 32, 40)
) -> Tuple[np.ndarray, int, int]:
    """Create a plain-coloured canvas (no tile download) for track-only map display."""
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    cx, cy = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
    tx, ty = ll_to_tile(cx, cy, zoom)
    half = grid // 2
    canvas = np.zeros((256 * grid, 256 * grid, 3), dtype=np.uint8)
    canvas[...] = bg
    return canvas, tx - half, ty - half
