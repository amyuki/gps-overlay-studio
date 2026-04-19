#!/usr/bin/env python3
"""
GPS Overlay Studio - Web UI
Run: python app.py
Visit: http://localhost:5000
"""

import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from web.preview import clean_path, extract_frame, quick_parse_gpx

app = Flask(__name__)
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

jobs: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/preview-gpx", methods=["POST"])
def preview_gpx():
    data = request.json
    raw = (data.get("path") or "")
    path = raw.strip().strip('"').strip("'")

    # Try several path variants to handle copy-paste quirks across platforms
    candidates = list(dict.fromkeys([
        path,
        path.replace(chr(92) + chr(92), chr(92)),
        path.replace(chr(47), chr(92)),
        path.replace(chr(92), chr(47)),
        raw.strip(),
    ]))

    for p in candidates:
        if p and os.path.isfile(p):
            print(f"[GPX] Found file: {p}", flush=True)
            return jsonify(quick_parse_gpx(p))

    print(f"[GPX] Raw path: {repr(raw)}", flush=True)
    print(f"[GPX] Cleaned: {repr(path)}", flush=True)
    try:
        parent = os.path.dirname(path)
        if parent and os.path.isdir(parent):
            gpx_files = [f for f in os.listdir(parent) if f.lower().endswith(".gpx")]
            print(f"[GPX] GPX files in directory: {gpx_files}", flush=True)
            hint = f"GPX files in directory: {gpx_files}" if gpx_files else "Directory exists but contains no GPX files"
        else:
            print(f"[GPX] Parent directory not found: {repr(parent)}", flush=True)
            hint = f"Directory not found: {parent}"
    except Exception as e:
        hint = str(e)

    return jsonify({"ok": False, "error": f"Not found: {repr(path)} | {hint}"})


@app.route("/preview-frame", methods=["POST"])
def preview_frame():
    data = request.json or {}
    path = clean_path(data.get("path", ""))
    pos = float(data.get("pos", 0.4))
    return jsonify(extract_frame(path, pos))


@app.route("/render", methods=["POST"])
def render():
    data = request.json
    job_id = str(uuid.uuid4())
    out_path = clean_path(data.get("output_path") or "") or str(OUTPUT_DIR / f"{job_id}.mp4")

    jobs[job_id] = {"status": "running", "progress": 0, "logs": [], "output": out_path, "error": None}

    def run():
        script = Path(__file__).parent / "gps_overlay.py"
        cmd = [
            sys.executable, "-u", str(script),
            "--video",       clean_path(data["video_path"]),
            "--gpx",         clean_path(data["gpx_path"]),
            "--output",      out_path,
            "--widgets",     data.get("widgets", "map,speed,elevation"),
            "--position",    data.get("position", "top-left"),
            "--theme",       data.get("theme", "dark"),
            "--map-style",   data.get("map_style", "voyager"),
            "--zoom",        str(data.get("zoom", 15)),
            "--offset",      str(data.get("offset", 0)),
            "--encoder",     data.get("encoder", "cpu"),
            "--mode",        data.get("mode", "burn"),
            "--overlay-fmt", data.get("overlay_fmt", "prores"),
            "--opacity",     str(data.get("opacity", 82)),
            "--accent",      data.get("accent_color", ""),
            *(["--no-map-tiles"] if not data.get("load_map_tiles", False) else []),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            all_logs: list = []
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                if line.startswith("PROGRESS "):
                    parts = line.split()
                    try:
                        pct = float(parts[1])
                        jobs[job_id]["progress"] = pct
                        friendly = f"⏳ Rendering... {pct:.1f}%  {parts[2]}"
                        if all_logs and all_logs[-1].startswith("⏳"):
                            all_logs[-1] = friendly
                        else:
                            all_logs.append(friendly)
                    except Exception:
                        pass
                else:
                    all_logs.append(line)
                jobs[job_id]["logs"] = all_logs[-50:]
            proc.wait()
            if proc.returncode == 0:
                jobs[job_id].update(status="done", progress=100, output_path=out_path)
            else:
                jobs[job_id].update(status="error", error=f"Exit code {proc.returncode}")
        except Exception as e:
            jobs[job_id].update(status="error", error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status":      job["status"],
        "progress":    job["progress"],
        "logs":        job["logs"],
        "error":       job["error"],
        "output_path": job.get("output_path", ""),
    })


@app.route("/output/<job_id>")
def output(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "not ready"}), 404
    return send_file(
        job["output"],
        mimetype="video/mp4",
        as_attachment=True,
        download_name="gps_overlay.mp4",
    )


if __name__ == "__main__":
    print("\n🛰  GPS Overlay Studio v1.0")
    print("━" * 36)
    print("  http://localhost:5000")
    print("  Press Ctrl+C to quit\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
