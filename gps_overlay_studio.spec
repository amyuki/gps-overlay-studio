# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for GPS Overlay Studio
# Build:  pyinstaller gps_overlay_studio.spec

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static",    "static"),
    ],
    hiddenimports=[
        # Flask & Jinja
        "flask",
        "flask.templating",
        "jinja2",
        "jinja2.ext",
        "werkzeug",
        "werkzeug.serving",
        "werkzeug.debug",
        "click",
        "itsdangerous",
        # HTTP / networking
        "requests",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
        # Image / video
        "cv2",
        "numpy",
        "PIL",
        "PIL.Image",
        # pywebview — Windows EdgeChromium (WebView2) backend
        "webview",
        "webview.platforms",
        "webview.platforms.edgechromium",
        "webview.event",
        "webview.guilib",
        "webview.util",
        "clr",                          # pythonnet (used by pywebview on Windows)
        "clr_loader",
        # Project packages
        "gps_overlay",
        "gps_overlay.config",
        "gps_overlay.gpx",
        "gps_overlay.map_utils",
        "gps_overlay.drawing",
        "gps_overlay.widgets",
        "gps_overlay.renderer",
        "web",
        "web.preview",
        # Stdlib extras PyInstaller sometimes misses
        "xml.etree.ElementTree",
        "email",
        "email.mime",
        "email.mime.text",
        "urllib.request",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "setuptools",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gps-overlay-studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # windowed=True hides the console in normal use; the CLI render subprocess
    # inherits the parent's console so PROGRESS lines still reach the web UI.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    name="gps-overlay-studio",
)
