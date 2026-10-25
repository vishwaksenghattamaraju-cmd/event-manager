@echo off
REM One-click setup + run for Windows. Double-click this file.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || (echo Python 3.11+ is required. Install it from python.org and tick "Add to PATH". & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"
echo Installing requirements (first run takes a few minutes)...
python -m pip install -q -r requirements.txt || (echo Install failed. & pause & exit /b 1)
echo.
echo Starting app at http://127.0.0.1:5000  (press Ctrl+C to stop)
start "" http://127.0.0.1:5000
python backend\app.py
pause
