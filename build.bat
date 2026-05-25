@echo off
setlocal

echo ============================================================
echo  GPS Overlay Studio — Windows build
echo ============================================================
echo.

REM ── 1. Install / upgrade dependencies ────────────────────────
echo [1/3] Installing build dependencies...
pip install --upgrade pyinstaller pywebview
if errorlevel 1 (
    echo ERROR: pip install failed. Make sure Python is on PATH.
    pause & exit /b 1
)

REM ── 2. Clean previous build artefacts ────────────────────────
echo.
echo [2/3] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

REM ── 3. Build ──────────────────────────────────────────────────
echo.
echo [3/3] Running PyInstaller...
pyinstaller gps_overlay_studio.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed — see output above.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Output: dist\gps-overlay-studio\gps-overlay-studio.exe
echo.
echo  Double-click the exe  → native app window (Edge WebView2)
echo  Run with --browser    → opens in system browser instead
echo  Run with --video ...  → CLI renderer
echo.
echo  IMPORTANT: ffmpeg must be installed and on PATH for
echo  rendering to work (https://ffmpeg.org/download.html).
echo ============================================================
pause
