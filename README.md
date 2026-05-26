# GPS Overlay Studio

Burns GPS track data (speed, elevation, map, grade, distance) as visual overlays onto video files. Use the web UI for a live preview, or the CLI to script batch renders.

## Demo

[![GPS Overlay Studio demo](https://img.youtube.com/vi/NbdiBdZwiXg/maxresdefault.jpg)](https://youtu.be/NbdiBdZwiXg)

---

Two output modes:
- **Burn** — composites widgets directly onto the video (H.264 / NVENC)
- **Transparent Overlay** — generates an alpha-channel clip (ProRes 4444 or WebM VP9) for NLEs like DaVinci Resolve, Premiere, or Final Cut Pro

---

## Requirements

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/download.html) on your `PATH` (full build recommended — must include libx264; NVENC optional)
- NVIDIA GPU + driver ≥ 452.39 for `--encoder gpu`

```bash
pip install flask opencv-python numpy requests
```

---

## Quick start

### Web UI

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000), paste your file paths, and click **Start Render**.

### CLI

```bash
# Basic burn
python gps_overlay.py --video ride.mp4 --gpx track.gpx --output out.mp4

# Choose widgets and position
python gps_overlay.py --video ride.mp4 --gpx track.gpx \
  --widgets map,speed,elevation,grade,distance \
  --position top-right --theme dark

# Transparent overlay for DaVinci Resolve
python gps_overlay.py --video ride.mp4 --gpx track.gpx \
  --mode overlay --overlay-fmt prores --output overlay.mov

# GPU pipeline (CUDA decode + NVENC encode, ~10× faster at 4K)
python gps_overlay.py --video ride.mp4 --gpx track.gpx \
  --encoder gpu --map-style topo --zoom 16

# Track-only map (no internet required, default)
python gps_overlay.py --video ride.mp4 --gpx track.gpx --no-map-tiles

# Fix GPS/video clock drift
python gps_overlay.py --video ride.mp4 --gpx track.gpx --offset -30
```

---

## Web UI workflow

1. **Video path** — paste the full path to your video file
2. **GPX path** — paste the full path to your `.gpx` file; the canvas preview updates instantly
3. **Widgets** — toggle Map, Speed, Elevation, Grade, Distance
4. **Position** — top-left, top-right, bottom-left, bottom-right
5. **Style & Encoding** — output mode, encoder, theme, opacity, accent colour, map background, map style, zoom, and GPX time offset
6. **Start Render** — progress is shown live; download the finished file when done

**Map background** defaults to *Track Only* (no network requests). Switch to *Load Tiles* to fetch map tiles at render time (internet required).

---

## CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--video` | *(required)* | Input video path |
| `--gpx` | *(required)* | GPX file path |
| `--output` | `output.mp4` | Output file path |
| `--widgets` | `map,speed,elevation` | Comma-separated list |
| `--position` | `top-left` | `top-left` `top-right` `bottom-left` `bottom-right` |
| `--theme` | `dark` | `dark` or `light` |
| `--map-style` | `voyager` | `voyager` `dark` `light` `topo` |
| `--zoom` | `15` | Map zoom level (13–17) |
| `--no-map-tiles` | *(off)* | Skip tile download; render track path on plain canvas |
| `--offset` | `0.0` | GPX time offset in seconds (positive = GPS starts after video) |
| `--encoder` | `cpu` | `cpu` (libx264) or `gpu` (NVENC) |
| `--mode` | `burn` | `burn` or `overlay` |
| `--overlay-fmt` | `prores` | `prores` (`.mov`) or `webm` (`.webm`) |
| `--opacity` | `82` | Widget background opacity 0–100 |
| `--accent` | *(theme default)* | Accent colour hex, e.g. `#ff6600` |

---

## Widgets

| Widget | Size | Shows |
|--------|------|-------|
| `map` | 290×290 | Track path with current position arrow; optional tiled basemap |
| `speed` | 290×90 | Current speed in km/h with progress bar |
| `elevation` | 290×110 | Elevation line chart with current marker |
| `grade` | 290×70 | Slope percentage with centre-zero accent bar |
| `distance` | 290×70 | Cumulative distance with total progress bar |

All widget bars use the accent colour. The current position on the map is shown as a white circle with a red directional arrow.

---

## Encoder options

| Mode | Codec | Notes |
|------|-------|-------|
| CPU | `libx264` | Works everywhere; OpenCV decodes frames, Python composites widgets |
| GPU | `h264_nvenc` | Requires NVIDIA GPU + CUDA drivers; full ffmpeg pipeline (see below) |
| Overlay (ProRes) | `prores_ks -profile:v 4444` | Alpha channel, large file, NLE-compatible |
| Overlay (WebM) | `libvpx-vp9` | Alpha channel, smaller file, open source |

**GPU pipeline** (`--encoder gpu`): Python renders only the widget bounding box (≈700 KB/frame BGRA at 4K) and pipes it to ffmpeg. ffmpeg handles CUDA hardware decode of the source video, alpha-composites the widget layer via its `overlay` filter, and encodes with NVENC — all without routing full video frames through Python. At 4K/30fps this is typically **10× faster** than CPU mode (measured: ~140 fps vs ~13 fps).

---

## Map styles

| Value | Description |
|-------|-------------|
| `voyager` | Colourful street map (default) |
| `dark` | Dark basemap |
| `light` | Light basemap |
| `topo` | Topographic map |

Map tiles are fetched from [CARTO](https://carto.com) and [OpenTopoMap](https://opentopomap.org) at render time. Requires an internet connection. Use `--no-map-tiles` (or the *Track Only* toggle in the UI) to render without network access.

---

## Project structure

```
gps_overlay/          # Core rendering package
  __init__.py         # Re-exports full public API
  config.py           # Themes, map styles, layout constants
  gpx.py              # GPX parsing and time-index utilities
  map_utils.py        # Map tile fetching, plain canvas, coordinate helpers
  drawing.py          # OpenCV drawing helpers
  widgets.py          # Widget base class and all widget types
  renderer.py         # Render pipeline and CLI entry point

web/
  preview.py          # GPX preview parser for the web UI

templates/
  index.html          # Jinja2 template (served by Flask)

static/
  css/app.css         # UI styles
  js/app.js           # Canvas preview and polling logic

app.py                # Flask web server (routes only)
gps_overlay.py        # CLI entry point (thin wrapper)
test_gps_overlay.py   # 111 pytest tests
outputs/              # Default output folder (auto-created)
```

---

## Running tests

```bash
python -m pytest test_gps_overlay.py -v
```

All 111 tests run in under a second with no external dependencies (network, ffmpeg, or video files).
