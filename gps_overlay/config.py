"""Shared constants: themes, map styles, layout parameters."""

THEMES = {
    "dark": {
        "bg":           (15, 17, 20),
        "bg2":          (25, 28, 34),
        "border":       (45, 50, 60),
        "text":         (230, 235, 245),
        "text_muted":   (120, 130, 150),
        "accent":       (80, 210, 130),
        "accent2":      (60, 160, 255),
        "danger":       (80, 80, 230),
        "track_done":   (80, 200, 120),
        "track_future": (60,  65,  75),
        "dot":          (255, 255, 255),
        "chart_fill":   (40,  90,  55),
        "alpha":        210,
    },
    "light": {
        "bg":           (245, 247, 250),
        "bg2":          (255, 255, 255),
        "border":       (210, 215, 225),
        "text":         (30,  35,  45),
        "text_muted":   (130, 140, 160),
        "accent":       (40, 160,  80),
        "accent2":      (200, 100,  40),
        "danger":       (50,  50, 210),
        "track_done":   (50, 170,  90),
        "track_future": (180, 185, 195),
        "dot":          (20,  20,  20),
        "chart_fill":   (190, 230, 205),
        "alpha":        220,
    },
}

MAP_STYLES = {
    "voyager": "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    "dark":    "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    "topo":    "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
    "light":   "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
}

POSITION_ANCHOR = {
    "top-left":     "tl",
    "top-right":    "tr",
    "bottom-left":  "bl",
    "bottom-right": "br",
}

WIDGET_MARGIN = 20
WIDGET_GAP = 8


def apply_overrides(theme: dict, opacity: int = None, accent_hex: str = None) -> dict:
    """Return a copy of theme with optional opacity (0-100) and accent colour overrides."""
    t = dict(theme)
    if opacity is not None:
        t["alpha"] = max(0, min(255, round(opacity * 255 / 100)))
    if accent_hex:
        h = accent_hex.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        bgr = (b, g, r)  # RGB → BGR for OpenCV
        t["accent"] = bgr
        t["track_done"] = bgr
        t["chart_fill"] = tuple(max(0, c // 2) for c in bgr)
    return t
