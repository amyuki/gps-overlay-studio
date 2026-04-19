"""
Tests for gps_overlay.py

Run:
    python -m pytest test_gps_overlay.py -v
    python -m pytest test_gps_overlay.py -v --tb=short   # compact output
"""

import math
import os
import sys
import tempfile
import textwrap
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── import module under test ──────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
import gps_overlay as G


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures / helpers
# ══════════════════════════════════════════════════════════════════════════════

def make_point(lat, lon, ele=100.0, time=None):
    return {"lat": lat, "lon": lon, "ele": ele, "time": time}


def make_timed_point(lat, lon, ele, seconds_offset, t0=None):
    if t0 is None:
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t = t0 + timedelta(seconds=seconds_offset)
    return {"lat": lat, "lon": lon, "ele": ele, "time": t}


def straight_track(n=10, with_time=True):
    """Simple north-going track, 100 m between each point."""
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    points = []
    for i in range(n):
        lat = 45.0 + i * 0.0009  # ~100 m per step
        t = (t0 + timedelta(seconds=i * 10)) if with_time else None
        points.append({"lat": lat, "lon": 6.0, "ele": 200.0 + i * 10, "time": t})
    return points


def minimal_gpx(points) -> str:
    """Build a minimal GPX XML string from a list of dicts."""
    lines = ['<?xml version="1.0"?>',
             '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">',
             '<trk><trkseg>']
    for p in points:
        t_tag = f'<time>{p["time"].isoformat()}</time>' if p.get("time") else ""
        lines.append(
            f'<trkpt lat="{p["lat"]}" lon="{p["lon"]}">'
            f'<ele>{p["ele"]}</ele>{t_tag}</trkpt>'
        )
    lines += ['</trkseg></trk></gpx>']
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# haversine
# ══════════════════════════════════════════════════════════════════════════════

class TestHaversine:
    def test_same_point_is_zero(self):
        assert G.haversine(0, 0, 0, 0) == pytest.approx(0, abs=1e-6)

    def test_known_distance_equator(self):
        # 1 degree longitude at equator ≈ 111 320 m
        d = G.haversine(0, 0, 0, 1)
        assert d == pytest.approx(111_320, rel=0.01)

    def test_known_distance_latitude(self):
        # 1 degree latitude ≈ 111 000 m
        d = G.haversine(0, 0, 1, 0)
        assert d == pytest.approx(111_000, rel=0.01)

    def test_symmetry(self):
        d1 = G.haversine(45.0, 6.0, 45.1, 6.1)
        d2 = G.haversine(45.1, 6.1, 45.0, 6.0)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_antipodal_points(self):
        # Antipodal = half Earth circumference ≈ 20 015 km
        d = G.haversine(0, 0, 0, 180)
        assert d == pytest.approx(20_015_000, rel=0.01)

    def test_short_distance(self):
        # Two points ~14 m apart
        d = G.haversine(45.0, 6.0, 45.0001, 6.0001)
        assert 10 < d < 20


# ══════════════════════════════════════════════════════════════════════════════
# parse_gpx
# ══════════════════════════════════════════════════════════════════════════════

class TestParseGpx:
    def _write_gpx(self, content):
        f = tempfile.NamedTemporaryFile(suffix=".gpx", delete=False, mode="w")
        f.write(content)
        f.close()
        return f.name

    def test_parses_basic_trkpt(self):
        path = self._write_gpx(minimal_gpx([
            {"lat": 45.1, "lon": 6.2, "ele": 300.0,
             "time": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)},
        ]))
        pts = G.parse_gpx(path)
        os.unlink(path)
        assert len(pts) == 1
        assert pts[0]["lat"] == pytest.approx(45.1)
        assert pts[0]["lon"] == pytest.approx(6.2)
        assert pts[0]["ele"] == pytest.approx(300.0)
        assert pts[0]["time"] is not None

    def test_parses_multiple_points(self):
        raw = straight_track(5, with_time=True)
        path = self._write_gpx(minimal_gpx(raw))
        pts = G.parse_gpx(path)
        os.unlink(path)
        assert len(pts) == 5

    def test_handles_missing_elevation(self):
        gpx = textwrap.dedent("""\
            <?xml version="1.0"?>
            <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
            <trk><trkseg>
            <trkpt lat="45.0" lon="6.0"></trkpt>
            </trkseg></trk></gpx>""")
        path = self._write_gpx(gpx)
        pts = G.parse_gpx(path)
        os.unlink(path)
        assert pts[0]["ele"] == pytest.approx(0.0)

    def test_handles_missing_time(self):
        raw = [{"lat": 45.0, "lon": 6.0, "ele": 100.0, "time": None}]
        path = self._write_gpx(minimal_gpx(raw))
        pts = G.parse_gpx(path)
        os.unlink(path)
        assert pts[0]["time"] is None

    def test_nonexistent_file_raises(self):
        with pytest.raises(Exception):
            G.parse_gpx("/nonexistent/path/track.gpx")


# ══════════════════════════════════════════════════════════════════════════════
# enrich_points
# ══════════════════════════════════════════════════════════════════════════════

class TestEnrichPoints:
    def test_first_point_zeroed(self):
        pts = straight_track(3)
        enriched = G.enrich_points(pts)
        assert enriched[0]["speed"] == 0.0
        assert enriched[0]["dist"] == 0.0
        assert enriched[0]["grade"] == 0.0

    def test_distance_increases_monotonically(self):
        pts = G.enrich_points(straight_track(5))
        dists = [p["dist"] for p in pts]
        assert all(dists[i] <= dists[i+1] for i in range(len(dists)-1))

    def test_total_distance_reasonable(self):
        # 9 steps of ~100 m → ~0.9 km
        pts = G.enrich_points(straight_track(10))
        assert 0.8 < pts[-1]["dist"] < 1.1

    def test_speed_calculated_from_timestamps(self):
        pts = G.enrich_points(straight_track(3, with_time=True))
        # ~100 m in 10 s → ~36 km/h
        assert pts[1]["speed"] == pytest.approx(36, rel=0.15)

    def test_speed_zero_without_timestamps(self):
        pts = G.enrich_points(straight_track(3, with_time=False))
        assert all(p["speed"] == 0.0 for p in pts)

    def test_speed_capped_at_250(self):
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        pts = [
            {"lat": 45.0, "lon": 6.0, "ele": 0, "time": t0},
            # 1 degree lat in 1 second → impossibly fast
            {"lat": 46.0, "lon": 6.0, "ele": 0,
             "time": t0 + timedelta(seconds=1)},
        ]
        enriched = G.enrich_points(pts)
        assert enriched[1]["speed"] == pytest.approx(250.0)

    def test_grade_flat_is_zero(self):
        pts = [
            {"lat": 45.0, "lon": 6.0, "ele": 100.0, "time": None},
            {"lat": 45.001, "lon": 6.0, "ele": 100.0, "time": None},
        ]
        enriched = G.enrich_points(pts)
        assert enriched[1]["grade"] == pytest.approx(0.0)

    def test_grade_uphill_positive(self):
        pts = [
            {"lat": 45.0, "lon": 6.0, "ele": 100.0, "time": None},
            {"lat": 45.001, "lon": 6.0, "ele": 210.0, "time": None},  # +110 m
        ]
        enriched = G.enrich_points(pts)
        assert enriched[1]["grade"] > 0

    def test_grade_downhill_negative(self):
        pts = [
            {"lat": 45.0, "lon": 6.0, "ele": 300.0, "time": None},
            {"lat": 45.001, "lon": 6.0, "ele": 200.0, "time": None},
        ]
        enriched = G.enrich_points(pts)
        assert enriched[1]["grade"] < 0


# ══════════════════════════════════════════════════════════════════════════════
# make_time_index
# ══════════════════════════════════════════════════════════════════════════════

class TestMakeTimeIndex:
    def test_returns_none_without_timestamps(self):
        pts = straight_track(3, with_time=False)
        assert G.make_time_index(pts) is None

    def test_starts_at_zero(self):
        pts = straight_track(3, with_time=True)
        idx = G.make_time_index(pts)
        assert idx[0] == pytest.approx(0.0)

    def test_monotonically_increasing(self):
        pts = straight_track(5, with_time=True)
        idx = G.make_time_index(pts)
        assert all(idx[i] < idx[i+1] for i in range(len(idx)-1))

    def test_correct_intervals(self):
        # straight_track uses 10-second intervals
        pts = straight_track(4, with_time=True)
        idx = G.make_time_index(pts)
        assert idx[1] == pytest.approx(10.0)
        assert idx[2] == pytest.approx(20.0)
        assert idx[3] == pytest.approx(30.0)

    def test_interpolates_missing_timestamps(self):
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        pts = [
            {"lat": 45.0, "lon": 6.0, "ele": 0, "time": t0},
            {"lat": 45.001, "lon": 6.0, "ele": 0, "time": None},  # missing
            {"lat": 45.002, "lon": 6.0, "ele": 0,
             "time": t0 + timedelta(seconds=20)},
        ]
        idx = G.make_time_index(pts)
        assert idx is not None
        assert idx[1] == pytest.approx(10.0)  # interpolated midpoint

    def test_length_matches_points(self):
        pts = straight_track(7, with_time=True)
        idx = G.make_time_index(pts)
        assert len(idx) == 7


# ══════════════════════════════════════════════════════════════════════════════
# find_idx
# ══════════════════════════════════════════════════════════════════════════════

class TestFindIdx:
    @pytest.fixture
    def time_index(self):
        # 0, 10, 20, 30, 40 seconds
        return [float(i * 10) for i in range(5)]

    def test_returns_zero_for_none_index(self):
        assert G.find_idx(None, 5.0, 0.0) == 0

    def test_exact_match(self, time_index):
        assert G.find_idx(time_index, 20.0, 0.0) == 2

    def test_between_points_returns_earlier(self, time_index):
        assert G.find_idx(time_index, 15.0, 0.0) == 1

    def test_before_start_clamps_to_zero(self, time_index):
        assert G.find_idx(time_index, -5.0, 0.0) == 0

    def test_after_end_clamps_to_last(self, time_index):
        assert G.find_idx(time_index, 999.0, 0.0) == 4

    def test_positive_offset_shifts_earlier(self, time_index):
        # video_sec=20, offset=10 → t=30 → index 3
        assert G.find_idx(time_index, 20.0, 10.0) == 3

    def test_negative_offset_shifts_later(self, time_index):
        # video_sec=20, offset=-10 → t=10 → index 1
        assert G.find_idx(time_index, 20.0, -10.0) == 1

    def test_first_element(self, time_index):
        assert G.find_idx(time_index, 0.0, 0.0) == 0

    def test_last_element_exact(self, time_index):
        assert G.find_idx(time_index, 40.0, 0.0) == 4

    def test_single_element_index(self):
        assert G.find_idx([0.0], 50.0, 0.0) == 0


# ══════════════════════════════════════════════════════════════════════════════
# build_widgets
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildWidgets:
    def test_builds_all_known_widgets(self):
        theme = G.THEMES["dark"]
        widgets = G.build_widgets(["map", "speed", "elevation", "grade", "distance"], theme)
        assert len(widgets) == 5
        assert isinstance(widgets[0], G.MapWidget)
        assert isinstance(widgets[1], G.SpeedWidget)
        assert isinstance(widgets[2], G.ElevationWidget)
        assert isinstance(widgets[3], G.GradeWidget)
        assert isinstance(widgets[4], G.DistanceWidget)

    def test_skips_unknown_widget(self, capsys):
        theme = G.THEMES["dark"]
        widgets = G.build_widgets(["speed", "unknown_widget"], theme)
        assert len(widgets) == 1
        captured = capsys.readouterr()
        assert "unknown_widget" in captured.out

    def test_empty_list_returns_empty(self):
        assert G.build_widgets([], G.THEMES["dark"]) == []

    def test_strips_whitespace_from_names(self):
        theme = G.THEMES["dark"]
        widgets = G.build_widgets(["  speed  ", " map "], theme)
        assert len(widgets) == 2

    def test_light_theme_applied(self):
        theme = G.THEMES["light"]
        widgets = G.build_widgets(["speed"], theme)
        assert widgets[0].T == theme


# ══════════════════════════════════════════════════════════════════════════════
# compute_layout
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeLayout:
    MARGIN = 20
    GAP = 8

    @pytest.fixture
    def two_widgets(self):
        theme = G.THEMES["dark"]
        return [G.SpeedWidget(theme), G.ElevationWidget(theme)]

    def test_top_left_starts_at_margin(self, two_widgets):
        coords = G.compute_layout(two_widgets, "tl", 1920, 1080)
        assert coords[0] == (self.MARGIN, self.MARGIN)

    def test_top_right_x_near_right_edge(self, two_widgets):
        coords = G.compute_layout(two_widgets, "tr", 1920, 1080)
        ox = coords[0][0]
        assert ox + two_widgets[0].width() + self.MARGIN == pytest.approx(1920)

    def test_bottom_left_last_widget_near_bottom(self, two_widgets):
        coords = G.compute_layout(two_widgets, "bl", 1920, 1080)
        last_y = coords[-1][1] + two_widgets[-1].height()
        assert last_y + self.MARGIN == pytest.approx(1080)

    def test_bottom_right_position(self, two_widgets):
        coords = G.compute_layout(two_widgets, "br", 1920, 1080)
        ox = coords[0][0]
        last_y = coords[-1][1] + two_widgets[-1].height()
        assert ox + two_widgets[0].width() + self.MARGIN == pytest.approx(1920)
        assert last_y + self.MARGIN == pytest.approx(1080)

    def test_widgets_stacked_with_gap(self, two_widgets):
        coords = G.compute_layout(two_widgets, "tl", 1920, 1080)
        expected_y1 = coords[0][1] + two_widgets[0].height() + self.GAP
        assert coords[1][1] == expected_y1

    def test_single_widget_layout(self):
        theme = G.THEMES["dark"]
        widgets = [G.SpeedWidget(theme)]
        coords = G.compute_layout(widgets, "tl", 1920, 1080)
        assert len(coords) == 1
        assert coords[0] == (self.MARGIN, self.MARGIN)

    def test_empty_widgets_returns_empty(self):
        coords = G.compute_layout([], "tl", 1920, 1080)
        assert coords == []

    def test_all_widgets_share_same_x(self, two_widgets):
        coords = G.compute_layout(two_widgets, "tl", 1920, 1080)
        xs = [c[0] for c in coords]
        assert len(set(xs)) == 1  # all same x


# ══════════════════════════════════════════════════════════════════════════════
# Widget dimensions
# ══════════════════════════════════════════════════════════════════════════════

class TestWidgetDimensions:
    @pytest.mark.parametrize("widget_cls,expected_h", [
        (G.SpeedWidget,     90),
        (G.ElevationWidget, 110),
        (G.GradeWidget,     70),
        (G.DistanceWidget,  70),
    ])
    def test_height(self, widget_cls, expected_h):
        w = widget_cls(G.THEMES["dark"])
        assert w.height() == expected_h

    @pytest.mark.parametrize("widget_cls", [
        G.SpeedWidget, G.ElevationWidget, G.GradeWidget, G.DistanceWidget
    ])
    def test_default_width(self, widget_cls):
        w = widget_cls(G.THEMES["dark"])
        assert w.width() == 290

    def test_map_widget_dimensions(self):
        w = G.MapWidget(G.THEMES["dark"])
        assert w.height() == w.width()  # square
        assert w.height() > 200


# ══════════════════════════════════════════════════════════════════════════════
# Widget draw — smoke tests (don't crash, write pixels in right region)
# ══════════════════════════════════════════════════════════════════════════════

class TestWidgetDraw:
    @pytest.fixture
    def points(self):
        pts = G.enrich_points(straight_track(20, with_time=True))
        return pts

    @pytest.fixture
    def frame(self):
        return np.zeros((1080, 1920, 3), dtype=np.uint8)

    def test_speed_widget_draws_pixels(self, frame, points):
        w = G.SpeedWidget(G.THEMES["dark"])
        w.draw(frame, 20, 20, 10, points)
        region = frame[20:20+w.height(), 20:20+w.width()]
        assert region.max() > 0  # something was drawn

    def test_elevation_widget_draws_pixels(self, frame, points):
        w = G.ElevationWidget(G.THEMES["dark"])
        w.draw(frame, 20, 20, 10, points)
        region = frame[20:20+w.height(), 20:20+w.width()]
        assert region.max() > 0

    def test_grade_widget_draws_pixels(self, frame, points):
        w = G.GradeWidget(G.THEMES["dark"])
        w.draw(frame, 20, 20, 10, points)
        region = frame[20:20+w.height(), 20:20+w.width()]
        assert region.max() > 0

    def test_distance_widget_draws_pixels(self, frame, points):
        w = G.DistanceWidget(G.THEMES["dark"])
        w.draw(frame, 20, 20, 10, points)
        region = frame[20:20+w.height(), 20:20+w.width()]
        assert region.max() > 0

    def test_map_widget_without_canvas_does_not_crash(self, frame, points):
        w = G.MapWidget(G.THEMES["dark"])
        w.draw(frame, 20, 20, 10, points, map_canvas=None)
        # Should draw BG but not crash

    def test_draw_at_index_zero(self, frame, points):
        w = G.SpeedWidget(G.THEMES["dark"])
        w.draw(frame, 20, 20, 0, points)

    def test_draw_at_last_index(self, frame, points):
        w = G.SpeedWidget(G.THEMES["dark"])
        w.draw(frame, 20, 20, len(points) - 1, points)

    def test_light_theme_draws_differently(self, points):
        frame_dark  = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame_light = np.zeros((1080, 1920, 3), dtype=np.uint8)
        G.SpeedWidget(G.THEMES["dark"]).draw(frame_dark,  20, 20, 5, points)
        G.SpeedWidget(G.THEMES["light"]).draw(frame_light, 20, 20, 5, points)
        assert not np.array_equal(frame_dark, frame_light)

    def test_widget_stays_within_bounds(self, frame, points):
        """Widget should not write pixels far outside its declared area.

        cv2.addWeighted (used for semi-transparent BG) has a known 1-pixel
        off-by-one at the right/bottom edge. We allow a 2-pixel tolerance
        around the widget boundary and assert nothing beyond that changes.
        """
        w = G.SpeedWidget(G.THEMES["dark"])
        x, y = 20, 20
        h, ww = w.height(), w.width()
        TOLERANCE = 2  # px, for cv2 antialiasing / addWeighted edge effects

        before = frame.copy()
        w.draw(frame, x, y, 5, points)

        diff = (frame != before).any(axis=2)  # bool 2D mask of changed pixels
        rows, cols = np.where(diff)
        far_outside = [
            (r, c) for r, c in zip(rows, cols)
            if not (y - TOLERANCE <= r < y + h + TOLERANCE and
                    x - TOLERANCE <= c < x + ww + TOLERANCE)
        ]
        assert len(far_outside) == 0, (
            f"Widget wrote {len(far_outside)} pixels more than {TOLERANCE}px "
            f"outside its bounds ({x},{y} {ww}x{h}). "
            f"Sample: {far_outside[:5]}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# apply_overrides
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyOverrides:
    def test_no_overrides_returns_identical_values(self):
        base = G.THEMES["dark"]
        result = G.apply_overrides(base)
        assert result["alpha"] == base["alpha"]
        assert result["accent"] == base["accent"]

    def test_does_not_mutate_original_theme(self):
        base = G.THEMES["dark"]
        original_alpha = base["alpha"]
        G.apply_overrides(base, opacity=50)
        assert base["alpha"] == original_alpha

    def test_opacity_0_sets_alpha_0(self):
        result = G.apply_overrides(G.THEMES["dark"], opacity=0)
        assert result["alpha"] == 0

    def test_opacity_100_sets_alpha_255(self):
        result = G.apply_overrides(G.THEMES["dark"], opacity=100)
        assert result["alpha"] == 255

    def test_opacity_50_sets_alpha_near_128(self):
        result = G.apply_overrides(G.THEMES["dark"], opacity=50)
        assert abs(result["alpha"] - 128) <= 1

    def test_opacity_clamps_above_100(self):
        result = G.apply_overrides(G.THEMES["dark"], opacity=200)
        assert result["alpha"] == 255

    def test_opacity_clamps_below_0(self):
        result = G.apply_overrides(G.THEMES["dark"], opacity=-10)
        assert result["alpha"] == 0

    def test_accent_hex_converted_to_bgr(self):
        result = G.apply_overrides(G.THEMES["dark"], accent_hex="#ff6600")
        # #ff6600 → R=255 G=102 B=0 → BGR=(0, 102, 255)
        assert result["accent"] == (0, 102, 255)

    def test_accent_hex_with_no_hash(self):
        result = G.apply_overrides(G.THEMES["dark"], accent_hex="00ff00")
        assert result["accent"] == (0, 255, 0)

    def test_empty_accent_hex_leaves_accent_unchanged(self):
        base = G.THEMES["dark"]
        result = G.apply_overrides(base, accent_hex="")
        assert result["accent"] == base["accent"]

    def test_none_accent_hex_leaves_accent_unchanged(self):
        base = G.THEMES["dark"]
        result = G.apply_overrides(base, accent_hex=None)
        assert result["accent"] == base["accent"]

    def test_combined_opacity_and_accent(self):
        result = G.apply_overrides(G.THEMES["dark"], opacity=80, accent_hex="#ffffff")
        assert result["alpha"] == round(80 * 255 / 100)
        assert result["accent"] == (255, 255, 255)

    def test_light_theme_overrides_independently(self):
        dark_result  = G.apply_overrides(G.THEMES["dark"],  opacity=60)
        light_result = G.apply_overrides(G.THEMES["light"], opacity=60)
        assert dark_result["alpha"] == light_result["alpha"]
        assert dark_result["bg"] != light_result["bg"]

    def test_accent_override_also_sets_track_done(self):
        result = G.apply_overrides(G.THEMES["dark"], accent_hex="#ff6600")
        assert result["track_done"] == result["accent"]

    def test_accent_override_also_sets_chart_fill(self):
        # chart_fill should be a darker (half-intensity) version of the accent BGR
        result = G.apply_overrides(G.THEMES["dark"], accent_hex="#ff6600")
        expected_fill = tuple(max(0, c // 2) for c in result["accent"])
        assert result["chart_fill"] == expected_fill

    def test_no_accent_override_leaves_track_done_unchanged(self):
        base = G.THEMES["dark"]
        result = G.apply_overrides(base)
        assert result["track_done"] == base["track_done"]

    def test_no_accent_override_leaves_chart_fill_unchanged(self):
        base = G.THEMES["dark"]
        result = G.apply_overrides(base)
        assert result["chart_fill"] == base["chart_fill"]


# ══════════════════════════════════════════════════════════════════════════════
# Widget border (_bg fix)
# ══════════════════════════════════════════════════════════════════════════════

class TestWidgetNoBorder:
    """Verify _bg() does NOT draw an explicit border rectangle (border was removed per UX request)."""

    def _corner_pixels(self, widget_cls, x=20, y=20):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        w = widget_cls(G.THEMES["dark"])
        w.draw(frame, x, y, 0, G.enrich_points(straight_track(10, with_time=True)))
        ww, wh = w.width(), w.height()
        border_color = np.array(G.THEMES["dark"]["border"])
        top_right    = frame[y,          x + ww - 1]
        bottom_right = frame[y + wh - 1, x + ww - 1]
        return top_right, bottom_right, border_color

    def test_speed_widget_no_border(self):
        tr, br, bc = self._corner_pixels(G.SpeedWidget)
        assert not np.array_equal(tr, bc)
        assert not np.array_equal(br, bc)

    def test_elevation_widget_no_border(self):
        tr, br, bc = self._corner_pixels(G.ElevationWidget)
        assert not np.array_equal(tr, bc)
        assert not np.array_equal(br, bc)

    def test_grade_widget_no_border(self):
        tr, br, bc = self._corner_pixels(G.GradeWidget)
        assert not np.array_equal(tr, bc)
        assert not np.array_equal(br, bc)

    def test_distance_widget_no_border(self):
        tr, br, bc = self._corner_pixels(G.DistanceWidget)
        assert not np.array_equal(tr, bc)
        assert not np.array_equal(br, bc)


# ══════════════════════════════════════════════════════════════════════════════
# clean_path (from app.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestCleanPath:
    @pytest.fixture(autouse=True)
    def import_app(self):
        import app as A
        self.clean = A.clean_path

    def test_strips_double_quotes(self):
        assert self.clean('"C:\\path\\file.mp4"') == "C:\\path\\file.mp4"

    def test_strips_single_quotes(self):
        assert self.clean("'/home/user/file.gpx'") == "/home/user/file.gpx"

    def test_strips_whitespace(self):
        assert self.clean("  /home/user/file.gpx  ") == "/home/user/file.gpx"

    def test_strips_quotes_and_whitespace(self):
        assert self.clean('  "D:\\Videos\\ride.mp4"  ') == "D:\\Videos\\ride.mp4"

    def test_empty_string(self):
        assert self.clean("") == ""

    def test_none_returns_empty(self):
        assert self.clean(None) == ""

    def test_normal_path_unchanged(self):
        assert self.clean("/home/user/track.gpx") == "/home/user/track.gpx"

    def test_windows_path_unchanged(self):
        p = "D:\\Projects\\gpx\\track.gpx"
        assert self.clean(p) == p


# ══════════════════════════════════════════════════════════════════════════════
# quick_parse_gpx (from app.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestQuickParseGpx:
    @pytest.fixture(autouse=True)
    def import_app(self):
        import app as A
        self.parse = A.quick_parse_gpx

    def _write_gpx(self, points):
        f = tempfile.NamedTemporaryFile(suffix=".gpx", delete=False, mode="w")
        f.write(minimal_gpx(points))
        f.close()
        return f.name

    def test_returns_ok_true(self):
        pts = straight_track(5, with_time=True)
        path = self._write_gpx(pts)
        result = self.parse(path)
        os.unlink(path)
        assert result["ok"] is True

    def test_count_matches(self):
        pts = straight_track(8, with_time=True)
        path = self._write_gpx(pts)
        result = self.parse(path)
        os.unlink(path)
        assert result["count"] == 8

    def test_ele_min_max(self):
        pts = straight_track(5, with_time=True)  # ele 200..240
        path = self._write_gpx(pts)
        result = self.parse(path)
        os.unlink(path)
        assert result["ele_min"] == pytest.approx(200, abs=1)
        assert result["ele_max"] == pytest.approx(240, abs=1)

    def test_total_km_positive(self):
        pts = straight_track(10, with_time=True)
        path = self._write_gpx(pts)
        result = self.parse(path)
        os.unlink(path)
        assert result["total_km"] > 0

    def test_track_normalized_0_to_1(self):
        pts = straight_track(5, with_time=True)
        path = self._write_gpx(pts)
        result = self.parse(path)
        os.unlink(path)
        xs = [p["x"] for p in result["track"]]
        ys = [p["y"] for p in result["track"]]
        assert min(xs) >= 0 and max(xs) <= 1
        assert min(ys) >= 0 and max(ys) <= 1

    def test_returns_error_for_bad_path(self):
        result = self.parse("/nonexistent/track.gpx")
        assert result["ok"] is False
        assert "error" in result

    def test_too_few_points_returns_error(self):
        pts = straight_track(1, with_time=True)
        path = self._write_gpx(pts)
        result = self.parse(path)
        os.unlink(path)
        assert result["ok"] is False

    def test_has_time_flag(self):
        pts_with = straight_track(3, with_time=True)
        pts_without = straight_track(3, with_time=False)
        p1 = self._write_gpx(pts_with)
        p2 = self._write_gpx(pts_without)
        r1 = self.parse(p1)
        r2 = self.parse(p2)
        os.unlink(p1); os.unlink(p2)
        assert r1["has_time"] is True
        assert r2["has_time"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Integration: enrich → time_index → find_idx pipeline
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# build_plain_canvas
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildPlainCanvas:
    @pytest.fixture
    def pts(self):
        return G.enrich_points(straight_track(10, with_time=True))

    def test_returns_canvas_tx_ty(self, pts):
        canvas, tx, ty = G.build_plain_canvas(pts, zoom=15)
        assert canvas is not None
        assert isinstance(tx, int)
        assert isinstance(ty, int)

    def test_canvas_shape_is_grid_x_256(self, pts):
        canvas, _, _ = G.build_plain_canvas(pts, zoom=15, grid=5)
        assert canvas.shape == (256 * 5, 256 * 5, 3)

    def test_canvas_filled_with_bg_color(self, pts):
        bg = (10, 20, 30)
        canvas, _, _ = G.build_plain_canvas(pts, zoom=15, bg=bg)
        assert np.all(canvas[:, :, 0] == bg[0])
        assert np.all(canvas[:, :, 1] == bg[1])
        assert np.all(canvas[:, :, 2] == bg[2])

    def test_custom_grid_size(self, pts):
        canvas, _, _ = G.build_plain_canvas(pts, zoom=14, grid=3)
        assert canvas.shape == (256 * 3, 256 * 3, 3)


class TestPipeline:
    def test_full_pipeline_finds_correct_point(self):
        pts = G.enrich_points(straight_track(10, with_time=True))
        time_index = G.make_time_index(pts)
        # Each point is 10 s apart; at t=25s we expect index 2
        idx = G.find_idx(time_index, 25.0, 0.0)
        assert idx == 2

    def test_offset_shifts_index(self):
        pts = G.enrich_points(straight_track(10, with_time=True))
        time_index = G.make_time_index(pts)
        # Without offset at t=20 → index 2; with offset +10 → t=30 → index 3
        assert G.find_idx(time_index, 20.0, 0.0) == 2
        assert G.find_idx(time_index, 20.0, 10.0) == 3

    def test_parse_enrich_cycle(self):
        raw = straight_track(5, with_time=True)
        f = tempfile.NamedTemporaryFile(suffix=".gpx", delete=False, mode="w")
        f.write(minimal_gpx(raw))
        f.close()
        pts = G.enrich_points(G.parse_gpx(f.name))
        os.unlink(f.name)
        assert len(pts) == 5
        assert pts[-1]["dist"] > 0
        assert "speed" in pts[1]
        assert "grade" in pts[1]