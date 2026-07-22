@echo off
REM ============================================================
REM  Double-click this file to start the OT Prospector web app.
REM  It opens http://localhost:5000 in your browser.
REM  Close this window (or press Ctrl+C) to stop the server.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Could not find the virtual environment ^(.venv^).
  echo Run setup first:  python -m venv .venv  ^&^&  .venv\Scripts\python -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo Starting OT Prospector...
".venv\Scripts\python.exe" webapp\app.py

echo.
echo Server stopped.
pause
