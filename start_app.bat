@echo off
REM One-click setup + run for Windows. Double-click this file.
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else (
  REM Try creating virtualenv; if OneDrive blocks, fall back to system python
  python -m venv .venv 2>nul
  if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
)

echo.
echo Starting Event Inventory AI at http://127.0.0.1:5000 ...
echo (Press Ctrl+C in this window to stop the server)
echo.
start "" http://127.0.0.1:5000
python backend\app.py
pause
