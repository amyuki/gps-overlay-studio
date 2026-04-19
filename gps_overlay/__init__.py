"""GPS Overlay - public API."""

from .config import MAP_STYLES, POSITION_ANCHOR, THEMES, apply_overrides
from .drawing import alpha_rect, put_text, text_size
from .gpx import enrich_points, find_idx, haversine, make_time_index, parse_gpx
from .map_utils import build_map_canvas, build_plain_canvas, fetch_tile, ll_to_px, ll_to_tile
from .renderer import build_widgets, check_ffmpeg_encoder, compute_layout, process_video
from .widgets import (
    WIDGET_MAP,
    DistanceWidget,
    ElevationWidget,
    GradeWidget,
    MapWidget,
    SpeedWidget,
    Widget,
)

__all__ = [
    # config
    "THEMES", "MAP_STYLES", "POSITION_ANCHOR", "apply_overrides",
    # gpx
    "haversine", "parse_gpx", "enrich_points", "make_time_index", "find_idx",
    # map
    "ll_to_tile", "ll_to_px", "fetch_tile", "build_map_canvas", "build_plain_canvas",
    # drawing
    "alpha_rect", "put_text", "text_size",
    # widgets
    "Widget", "MapWidget", "SpeedWidget", "ElevationWidget", "GradeWidget", "DistanceWidget",
    "WIDGET_MAP",
    # renderer
    "build_widgets", "compute_layout", "check_ffmpeg_encoder", "process_video",
]
