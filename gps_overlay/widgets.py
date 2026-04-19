"""Widget system: base class and all concrete overlay widgets."""

import math
from typing import Dict, List, Optional, Type

import cv2
import numpy as np

from .drawing import alpha_rect, put_text, text_size
from .map_utils import ll_to_px


class Widget:
    """Base class for all overlay widgets."""

    PAD = 12

    def __init__(self, theme: dict) -> None:
        self.T = theme

    def height(self) -> int:
        raise NotImplementedError

    def width(self) -> int:
        return 290

    def draw(self, img: np.ndarray, x: int, y: int, idx: int, points: List[dict], **kwargs) -> None:
        raise NotImplementedError

    def _bg(self, img: np.ndarray, x: int, y: int) -> None:
        alpha_rect(img, x, y, self.width(), self.height(), self.T["bg"], self.T["alpha"])
        cv2.rectangle(img, (x, y), (x + 3, y + self.height()), self.T["accent"], -1)

    def _label(self, img: np.ndarray, x: int, y: int, text: str) -> None:
        put_text(img, text, x + self.PAD, y + self.PAD + 12, size=0.38, color=self.T["text_muted"])


# ── Map ────────────────────────────────────────────────────────────────────────

class MapWidget(Widget):
    SIZE = 266

    # Class-level tile cache: keyed by id(map_canvas)
    _cache: Dict[int, dict] = {}

    def height(self) -> int:
        return self.SIZE + self.PAD * 2

    def width(self) -> int:
        return self.SIZE + self.PAD * 2

    def draw(
        self,
        img: np.ndarray,
        x: int, y: int,
        idx: int,
        points: List[dict],
        map_canvas: Optional[np.ndarray] = None,
        tx: int = 0,
        ty: int = 0,
        zoom: int = 15,
        **kwargs,
    ) -> None:
        self._bg(img, x, y)
        if map_canvas is None:
            return

        cur = points[idx]
        cpx, cpy = ll_to_px(cur["lat"], cur["lon"], tx, ty, zoom)

        h, w = map_canvas.shape[:2]
        half = self.SIZE // 2
        x0 = max(0, min(cpx - half, w - self.SIZE))
        y0 = max(0, min(cpy - half, h - self.SIZE))

        cache_key = id(map_canvas)
        cache = MapWidget._cache.get(cache_key)
        if cache is None:
            track_px = [ll_to_px(p["lat"], p["lon"], tx, ty, zoom) for p in points]
            base = map_canvas.copy()
            for i in range(1, len(track_px)):
                cv2.line(base, track_px[i - 1], track_px[i], self.T["track_future"], 2, cv2.LINE_AA)
            cache = {"track_px": track_px, "base": base}
            MapWidget._cache[cache_key] = cache

        track_px = cache["track_px"]
        crop = cache["base"][y0:y0 + self.SIZE, x0:x0 + self.SIZE].copy()

        for i in range(1, min(idx + 1, len(track_px))):
            ax, ay = track_px[i - 1][0] - x0, track_px[i - 1][1] - y0
            bx, by = track_px[i][0] - x0, track_px[i][1] - y0
            if (-20 <= ax < self.SIZE + 20 or -20 <= bx < self.SIZE + 20) and \
               (-20 <= ay < self.SIZE + 20 or -20 <= by < self.SIZE + 20):
                cv2.line(crop, (ax, ay), (bx, by), self.T["track_done"], 4, cv2.LINE_AA)

        # Directional red arrow at current position
        n = len(points)
        ppx = track_px[max(0, idx - 1)]
        npx = track_px[min(idx + 1, n - 1)]
        adx, ady = npx[0] - ppx[0], npx[1] - ppx[1]
        angle = math.atan2(ady, adx) if (adx or ady) else 0.0
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        cx_c, cy_c = cpx - x0, cpy - y0
        sz = 10
        tip   = (int(cx_c + sz * cos_a),                              int(cy_c + sz * sin_a))
        left  = (int(cx_c - sz * 0.5 * cos_a - sz * 0.6 * sin_a),    int(cy_c - sz * 0.5 * sin_a + sz * 0.6 * cos_a))
        right = (int(cx_c - sz * 0.5 * cos_a + sz * 0.6 * sin_a),    int(cy_c - sz * 0.5 * sin_a - sz * 0.6 * cos_a))
        cv2.circle(crop, (cx_c, cy_c), 12, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.fillPoly(crop, [np.array([tip, left, right], np.int32)], (0, 0, 255), cv2.LINE_AA)

        mx2, my2 = x + self.PAD, y + self.PAD
        img[my2:my2 + self.SIZE, mx2:mx2 + self.SIZE] = crop


# ── Speed ──────────────────────────────────────────────────────────────────────

class SpeedWidget(Widget):
    def height(self) -> int:
        return 90

    def draw(self, img: np.ndarray, x: int, y: int, idx: int, points: List[dict], **kwargs) -> None:
        self._bg(img, x, y)
        T = self.T
        speed = points[idx]["speed"]

        self._label(img, x, y, "SPEED")

        val = f"{speed:.0f}"
        tw, _ = text_size(val, size=2.0, thick=3)
        put_text(img, val, x + self.PAD, y + self.height() - 16, size=2.0, color=T["accent"], thick=3, bold=True)
        put_text(img, "km/h", x + self.PAD + tw + 12, y + self.height() - 20, size=0.5, color=T["text_muted"])

        max_speed = max(p["speed"] for p in points) or 1
        bar_ratio = speed / max_speed
        bx, by = x + self.PAD, y + self.height() - 6
        bw = self.width() - self.PAD * 2
        cv2.rectangle(img, (bx, by), (bx + bw, by + 3), T["bg2"], -1)
        cv2.rectangle(img, (bx, by), (bx + int(bw * bar_ratio), by + 3), T["accent"], -1)


# ── Elevation ──────────────────────────────────────────────────────────────────

class ElevationWidget(Widget):
    def height(self) -> int:
        return 110

    def draw(self, img: np.ndarray, x: int, y: int, idx: int, points: List[dict], **kwargs) -> None:
        self._bg(img, x, y)
        T = self.T

        eles = [p["ele"] for p in points]
        e_min, e_max = min(eles), max(eles)
        e_range = max(e_max - e_min, 1)
        cur_ele = points[idx]["ele"]

        self._label(img, x, y, "ELEVATION")
        put_text(img, f"{cur_ele:.0f} m", x + self.PAD, y + 44, size=0.9, color=T["text"], thick=2, bold=True)
        put_text(img, f"▲{e_max:.0f}m", x + self.width() - 80, y + 30, size=0.35, color=T["text_muted"])
        put_text(img, f"▼{e_min:.0f}m", x + self.width() - 80, y + 46, size=0.35, color=T["text_muted"])

        cx0, cy0 = x + self.PAD, y + 55
        cw, ch = self.width() - self.PAD * 2, self.height() - 65
        n = len(points)
        step = max(1, n // cw)

        poly_pts = [(cx0, cy0 + ch)]
        for i in range(0, n, step):
            px2 = cx0 + int(i / n * cw)
            norm = (points[i]["ele"] - e_min) / e_range
            py2 = cy0 + ch - int(norm * ch)
            poly_pts.append((px2, py2))
        poly_pts.append((cx0 + cw, cy0 + ch))

        overlay = img.copy()
        cv2.fillPoly(overlay, [np.array(poly_pts, np.int32)], T["chart_fill"])
        cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)

        prev = None
        for i in range(0, n, step):
            px2 = cx0 + int(i / n * cw)
            norm = (points[i]["ele"] - e_min) / e_range
            py2 = cy0 + ch - int(norm * ch)
            pt = (px2, py2)
            if prev:
                col = T["accent"] if i <= idx else T["track_future"]
                cv2.line(img, prev, pt, col, 2, cv2.LINE_AA)
            prev = pt

        cur_x = cx0 + int(idx / max(n - 1, 1) * cw)
        cv2.line(img, (cur_x, cy0), (cur_x, cy0 + ch), T["dot"], 1, cv2.LINE_AA)
        norm = (cur_ele - e_min) / e_range
        cur_y2 = cy0 + ch - int(norm * ch)
        cv2.circle(img, (cur_x, cur_y2), 4, T["accent"], -1, cv2.LINE_AA)


# ── Grade ──────────────────────────────────────────────────────────────────────

class GradeWidget(Widget):
    def height(self) -> int:
        return 70

    def draw(self, img: np.ndarray, x: int, y: int, idx: int, points: List[dict], **kwargs) -> None:
        self._bg(img, x, y)
        T = self.T
        grade = points[idx]["grade"]

        self._label(img, x, y, "GRADE")

        color = T["danger"] if abs(grade) > 8 else T["accent"] if abs(grade) > 3 else T["text"]
        sign = "+" if grade > 0 else ""
        put_text(img, f"{sign}{grade:.1f}%", x + self.PAD, y + self.height() - 16, size=1.1, color=color, thick=2, bold=True)

        bx, by = x + self.PAD, y + self.height() - 6
        bw = self.width() - self.PAD * 2
        mid = bx + bw // 2
        cv2.rectangle(img, (bx, by), (bx + bw, by + 3), T["bg2"], -1)
        ratio = max(-1, min(1, grade / 20))
        if ratio > 0:
            cv2.rectangle(img, (mid, by), (mid + int(bw // 2 * ratio), by + 3), T["accent"], -1)
        else:
            cv2.rectangle(img, (mid + int(bw // 2 * ratio), by), (mid, by + 3), T["accent"], -1)
        cv2.rectangle(img, (mid - 1, by - 1), (mid + 1, by + 4), T["text_muted"], -1)


# ── Distance ───────────────────────────────────────────────────────────────────

class DistanceWidget(Widget):
    def height(self) -> int:
        return 70

    def draw(self, img: np.ndarray, x: int, y: int, idx: int, points: List[dict], **kwargs) -> None:
        self._bg(img, x, y)
        T = self.T
        dist = points[idx]["dist"]
        total = points[-1]["dist"]

        self._label(img, x, y, "DISTANCE")
        put_text(img, f"{dist:.2f}", x + self.PAD, y + self.height() - 16, size=1.1, color=T["accent"], thick=2, bold=True)
        put_text(img, f"/ {total:.1f} km", x + self.PAD + 80, y + self.height() - 20, size=0.45, color=T["text_muted"])

        bx, by = x + self.PAD, y + self.height() - 6
        bw = self.width() - self.PAD * 2
        ratio = dist / total if total > 0 else 0
        cv2.rectangle(img, (bx, by), (bx + bw, by + 3), T["bg2"], -1)
        cv2.rectangle(img, (bx, by), (bx + int(bw * ratio), by + 3), T["accent"], -1)


# ── Registry ───────────────────────────────────────────────────────────────────

WIDGET_MAP: Dict[str, Type[Widget]] = {
    "map":       MapWidget,
    "speed":     SpeedWidget,
    "elevation": ElevationWidget,
    "grade":     GradeWidget,
    "distance":  DistanceWidget,
}
