"""Rendering pipeline: widget layout, ffmpeg encoding, CLI entry point."""

import argparse
import os
import subprocess
import sys
import threading
from typing import List, Tuple

from .config import MAP_STYLES, POSITION_ANCHOR, THEMES, WIDGET_GAP, WIDGET_MARGIN, apply_overrides
from .gpx import enrich_points, find_idx, make_time_index, parse_gpx
from .map_utils import build_map_canvas, build_plain_canvas
from .widgets import MapWidget, Widget, WIDGET_MAP

import cv2
import numpy as np


def build_widgets(widget_names: List[str], theme: dict) -> List[Widget]:
    """Instantiate widgets by name, skipping unknown names with a warning."""
    out = []
    for name in widget_names:
        cls = WIDGET_MAP.get(name.strip().lower())
        if cls:
            out.append(cls(theme))
        else:
            print(f"[WARNING] Unknown widget: {name}, skipping")
    return out


def compute_layout(
    widgets: List[Widget], anchor: str, video_w: int, video_h: int
) -> List[Tuple[int, int]]:
    """Return the top-left (x, y) coordinate for each widget given the anchor."""
    if not widgets:
        return []

    total_h = sum(w.height() for w in widgets) + WIDGET_GAP * (len(widgets) - 1)
    max_w = max(w.width() for w in widgets)

    if anchor == "tl":
        ox, oy = WIDGET_MARGIN, WIDGET_MARGIN
    elif anchor == "tr":
        ox, oy = video_w - max_w - WIDGET_MARGIN, WIDGET_MARGIN
    elif anchor == "bl":
        ox, oy = WIDGET_MARGIN, video_h - total_h - WIDGET_MARGIN
    else:  # br
        ox, oy = video_w - max_w - WIDGET_MARGIN, video_h - total_h - WIDGET_MARGIN

    coords, cy = [], oy
    for w in widgets:
        coords.append((ox, cy))
        cy += w.height() + WIDGET_GAP
    return coords


def check_ffmpeg_encoder(encoder: str) -> bool:
    """Return True if ffmpeg was built with the given encoder."""
    try:
        r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        return encoder in r.stdout
    except Exception:
        return False


def _render_overlay(args, points, widgets, coords, map_canvas, tx, ty, fps, total, vw, vh):
    """Generate a transparent video overlay (ProRes 4444 or WebM VP9)."""
    import subprocess as sp

    fmt = getattr(args, "overlay_fmt", "prores")
    if fmt == "prores":
        ffmpeg_codec = ["prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
        out = args.output if args.output.endswith(".mov") else args.output.replace(".mp4", ".mov")
        print("[ENCODE] ProRes 4444 Transparent Overlay (.mov)", flush=True)
    else:
        ffmpeg_codec = ["libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "20"]
        out = args.output if args.output.endswith(".webm") else args.output.replace(".mp4", ".webm")
        print("[ENCODE] WebM VP9 Transparent Overlay (.webm)", flush=True)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{vw}x{vh}", "-pix_fmt", "bgra", "-r", str(fps),
        "-i", "pipe:0",
        "-vcodec", *ffmpeg_codec,
        "-an",
        out,
    ]
    ffmpeg_proc = sp.Popen(ffmpeg_cmd, stdin=sp.PIPE, stderr=sp.PIPE)
    stderr_lines: List[str] = []

    def drain_stderr():
        for line in ffmpeg_proc.stderr:
            stderr_lines.append(line.decode(errors="replace").rstrip())

    threading.Thread(target=drain_stderr, daemon=True).start()

    duration = total / fps
    time_index = make_time_index(points)
    report_interval = max(1, total // 100)

    print(f"[Rendering] Generating transparent overlay, {total} frames...", flush=True)
    for fi in range(total):
        video_sec = fi / fps
        if time_index:
            idx = find_idx(time_index, video_sec, args.offset)
        else:
            idx = int(video_sec / duration * (len(points) - 1))
        idx = max(0, min(idx, len(points) - 1))

        frame_bgr = np.zeros((vh, vw, 3), dtype=np.uint8)
        alpha_ch = np.zeros((vh, vw), dtype=np.uint8)
        for widget, (wx, wy) in zip(widgets, coords):
            ww, wh = widget.width(), widget.height()
            widget.draw(frame_bgr, wx, wy, idx, points, map_canvas=map_canvas, tx=tx, ty=ty, zoom=args.zoom)
            y1, y2 = max(0, wy), min(vh, wy + wh)
            x1, x2 = max(0, wx), min(vw, wx + ww)
            alpha_ch[y1:y2, x1:x2] = 255

        frame_bgra = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2BGRA)
        frame_bgra[:, :, 3] = alpha_ch

        try:
            ffmpeg_proc.stdin.write(frame_bgra.tobytes())
        except BrokenPipeError:
            print("❌ ffmpeg pipe broken", flush=True)
            break

        if (fi + 1) % report_interval == 0 or fi + 1 == total:
            pct = (fi + 1) / total * 100
            print(f"PROGRESS {pct:.1f} ({fi+1}/{total})", flush=True)

    try:
        ffmpeg_proc.stdin.close()
    except Exception:
        pass
    ffmpeg_proc.wait()

    if ffmpeg_proc.returncode == 0:
        print(f"PROGRESS 100.0 ({total}/{total})", flush=True)
        print(f"✅ Done: {out}", flush=True)
        print("[Hint] Overlay this file on the video track in DaVinci/Premiere", flush=True)
    else:
        err = "\n".join(stderr_lines[-20:])
        print(f"❌ ffmpeg error:\n{err}", flush=True)
        sys.exit(1)


def _render_burn(args, points, widgets, coords, map_canvas, tx, ty, cap, fps, total, vw, vh):
    """Burn widgets directly onto the video frames (libx264 or NVIDIA NVENC)."""
    import subprocess as sp

    encoder = getattr(args, "encoder", "cpu")
    if encoder == "gpu" and check_ffmpeg_encoder("h264_nvenc"):
        ffmpeg_codec = ["h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "20"]
        print("[ENCODE] ✅ GPU (NVIDIA NVENC h264)", flush=True)
    else:
        if encoder == "gpu":
            print("[ENCODE] ⚠️  NVENC unavailable, falling back to CPU", flush=True)
        ffmpeg_codec = ["libx264", "-preset", "fast", "-crf", "18"]
        print("[ENCODE] CPU (libx264)", flush=True)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{vw}x{vh}", "-pix_fmt", "bgr24", "-r", str(fps),
        "-i", "pipe:0",
        "-i", args.video,
        "-map", "0:v", "-map", "1:a?",
        "-vcodec", *ffmpeg_codec,
        "-acodec", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        args.output,
    ]
    ffmpeg_proc = sp.Popen(ffmpeg_cmd, stdin=sp.PIPE, stderr=sp.PIPE)
    stderr_lines: List[str] = []

    def drain_stderr():
        for line in ffmpeg_proc.stderr:
            stderr_lines.append(line.decode(errors="replace").rstrip())

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    duration = total / fps
    time_index = make_time_index(points)
    report_interval = max(1, total // 100)

    print(f"[RENDER] Processing {total} frames...", flush=True)
    fi = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        video_sec = fi / fps
        if time_index:
            idx = find_idx(time_index, video_sec, args.offset)
        else:
            idx = int(video_sec / duration * (len(points) - 1))
        idx = max(0, min(idx, len(points) - 1))

        for widget, (wx, wy) in zip(widgets, coords):
            widget.draw(frame, wx, wy, idx, points, map_canvas=map_canvas, tx=tx, ty=ty, zoom=args.zoom)

        try:
            ffmpeg_proc.stdin.write(frame.tobytes())
        except BrokenPipeError:
            print("❌ ffmpeg pipe broken", flush=True)
            break

        fi += 1
        if fi % report_interval == 0 or fi >= total:
            pct = fi / total * 100
            print(f"PROGRESS {pct:.1f} ({fi}/{total})", flush=True)

    try:
        ffmpeg_proc.stdin.close()
    except Exception:
        pass
    ffmpeg_proc.wait()
    stderr_thread.join(timeout=3)

    if ffmpeg_proc.returncode == 0:
        print(f"PROGRESS 100.0 ({total}/{total})", flush=True)
        print(f"✅ Done: {args.output}", flush=True)
    else:
        err = "\n".join(stderr_lines[-20:])
        print(f"❌ ffmpeg error:\n{err}", flush=True)
        sys.exit(1)


def process_video(args) -> None:
    """Main render orchestrator: parse GPX, open video, run widgets, encode output."""
    mode = getattr(args, "mode", "burn")

    points = parse_gpx(args.gpx)
    if len(points) < 2:
        sys.exit("[ERROR] Not enough GPX points")
    points = enrich_points(points)

    cap = cv2.VideoCapture(args.video)
    vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[VIDEO] {vw}x{vh} @ {fps:.2f}fps  duration={total/fps:.1f}s  frames={total}", flush=True)

    theme = THEMES[args.theme]
    opacity = getattr(args, "opacity", None)
    accent = getattr(args, "accent", "") or ""
    if opacity is not None or accent:
        theme = apply_overrides(theme, opacity=opacity, accent_hex=accent or None)
    widget_names = [w.strip() for w in args.widgets.split(",")]
    widgets = build_widgets(widget_names, theme)
    anchor = POSITION_ANCHOR.get(args.position, "tl")
    coords = compute_layout(widgets, anchor, vw, vh)

    map_canvas, tx, ty = None, 0, 0
    if any(isinstance(w, MapWidget) for w in widgets):
        if getattr(args, "no_map_tiles", False):
            map_canvas, tx, ty = build_plain_canvas(points, args.zoom, grid=5, bg=theme.get("bg2", (24, 32, 40)))
        else:
            url_tpl = MAP_STYLES.get(args.map_style, MAP_STYLES["voyager"])
            map_canvas, tx, ty = build_map_canvas(points, args.zoom, url_tpl, grid=5)

    if mode == "overlay":
        cap.release()
        _render_overlay(args, points, widgets, coords, map_canvas, tx, ty, fps, total, vw, vh)
    else:
        _render_burn(args, points, widgets, coords, map_canvas, tx, ty, cap, fps, total, vw, vh)
        cap.release()


def main() -> None:
    """CLI entry point."""
    p = argparse.ArgumentParser(
        description="GPS Overlay - Modular widget overlay system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available widgets: map, speed, elevation, grade, distance
Examples:
  python gps_overlay.py --video ride.mp4 --gpx track.gpx
  python gps_overlay.py --video ride.mp4 --gpx track.gpx --widgets map,speed,elevation --theme dark
  python gps_overlay.py --video ride.mp4 --gpx track.gpx --position bottom-right --map-style dark
  python gps_overlay.py --video ride.mp4 --gpx track.gpx --offset -30 --zoom 16
        """,
    )
    p.add_argument("--video",        required=True,  help="Input video path")
    p.add_argument("--gpx",          required=True,  help="GPX file path")
    p.add_argument("--output",       default="output.mp4", help="Output path")
    p.add_argument("--widgets",      default="map,speed,elevation",
                   help="Widgets to display, comma-separated (map,speed,elevation,grade,distance)")
    p.add_argument("--position",     default="top-left",
                   choices=["top-left", "top-right", "bottom-left", "bottom-right"])
    p.add_argument("--theme",        default="dark", choices=["dark", "light"])
    p.add_argument("--map-style",    default="voyager",
                   choices=["voyager", "dark", "topo", "light"])
    p.add_argument("--zoom",         type=int, default=15, help="Map zoom level (13-17)")
    p.add_argument("--offset",       type=float, default=0.0,
                   help="GPX time offset in seconds (positive = GPX starts after video)")
    p.add_argument("--encoder",      default="cpu", choices=["cpu", "gpu"],
                   help="Encoder: cpu=libx264, gpu=NVIDIA NVENC")
    p.add_argument("--mode",         default="burn", choices=["burn", "overlay"],
                   help="burn=Burn to Video, overlay=Generate Transparent Overlay")
    p.add_argument("--overlay-fmt",  default="prores", choices=["prores", "webm"],
                   help="Transparent Overlay Format: prores=ProRes4444(.mov), webm=VP9(.webm)")
    p.add_argument("--opacity",      type=int, default=None,
                   help="Widget background opacity 0-100 (default: theme default ~82)")
    p.add_argument("--accent",       default="",
                   help="Widget accent colour as hex, e.g. #ff6600 (default: theme default)")
    p.add_argument("--no-map-tiles", action="store_true", default=False,
                   help="Skip map tile download; show track on plain background")

    args = p.parse_args()

    if not os.path.exists(args.video):
        sys.exit(f"[ERROR] Video not found: {args.video}")
    if not os.path.exists(args.gpx):
        sys.exit(f"[ERROR] GPX not found: {args.gpx}")

    process_video(args)
