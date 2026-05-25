#!/usr/bin/env python3
"""
GPS Overlay Studio — unified entry point for the Windows executable.

Behaviour when run as an exe:
  No args            → native window (Edge WebView2 via pywebview)
  --browser          → open in system browser instead of native window
  --video <path> ... → CLI renderer (also used by the web UI's render subprocess)

Behaviour when run as `python launcher.py` (dev):
  Starts Flask and opens in the system browser (same as `python app.py`).
"""

import sys
import threading
import time
from pathlib import Path


def _output_dir() -> Path:
    """Writable outputs folder — next to the exe when frozen, cwd otherwise."""
    if getattr(sys, "frozen", False):
        d = Path(sys.executable).parent / "outputs"
    else:
        d = Path("outputs")
    d.mkdir(exist_ok=True)
    return d


def _patch_app(output_dir: Path):
    """Import app module and override OUTPUT_DIR before Flask starts."""
    import app as _app_module
    _app_module.OUTPUT_DIR = output_dir
    return _app_module.app          # the Flask application object


def _wait_for_flask(url: str, timeout: float = 8.0):
    """Block until Flask is accepting connections (or timeout)."""
    import urllib.request
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.3)
            return True
        except Exception:
            time.sleep(0.15)
    return False


# ─── Modes ───────────────────────────────────────────────────────────────────

def run_cli():
    """Forward to the CLI renderer (argparse picks up sys.argv)."""
    from gps_overlay.renderer import main as cli_main
    cli_main()


def run_native_window(output_dir: Path):
    """Start Flask in a thread, then open a native Edge WebView2 window."""
    import webview

    flask_app = _patch_app(output_dir)

    def _serve():
        flask_app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

    threading.Thread(target=_serve, daemon=True).start()

    if not _wait_for_flask("http://127.0.0.1:5000"):
        print("[ERROR] Flask did not start in time", flush=True)
        sys.exit(1)

    window = webview.create_window(
        "GPS Overlay Studio",
        "http://127.0.0.1:5000",
        width=1340,
        height=880,
        min_size=(900, 640),
        resizable=True,
    )
    webview.start()                 # blocks until the window is closed


def run_browser(output_dir: Path):
    """Start Flask and open the UI in the system browser."""
    import webbrowser

    flask_app = _patch_app(output_dir)

    def _open():
        time.sleep(1.2)
        webbrowser.open("http://localhost:5000")

    threading.Thread(target=_open, daemon=True).start()
    print("\n GPS Overlay Studio v1.0")
    print("━" * 36)
    print("  http://localhost:5000")
    print("  Press Ctrl+C to quit\n")
    flask_app.run(host="0.0.0.0", port=5000, debug=False)


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    out_dir = _output_dir()

    # CLI mode — triggered by --video (direct CLI use or Flask render subprocess).
    if any(a == "--video" for a in args):
        run_cli()
        return

    is_frozen = getattr(sys, "frozen", False)

    # --browser flag overrides native window (useful for debugging the frozen build).
    if "--browser" in args:
        run_browser(out_dir)
        return

    if is_frozen:
        # Default for the .exe: native window
        run_native_window(out_dir)
    else:
        # Dev: plain browser (no pywebview dependency required in dev)
        run_browser(out_dir)


if __name__ == "__main__":
    main()
