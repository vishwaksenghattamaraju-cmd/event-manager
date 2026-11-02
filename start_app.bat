@echo off
setlocal enabledelayedexpansion

REM =========================================================================
REM  The Matrix - Event Inventory Management System
REM  Automated, Cross-Computer Windows Portable Launcher
REM =========================================================================

title The Matrix - Event Inventory AI

cd /d "%~dp0"

echo =========================================================================
echo   Starting The Matrix - Event Inventory Management System
echo =========================================================================
echo.

REM 1. Detect Python
set "PY_CMD="
where python >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=py"
    )
)

if "!PY_CMD!"=="" (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.11 or newer from https://www.python.org/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [*] Detected Python interpreter: !PY_CMD!
!PY_CMD! --version

REM 2. Verify or create local virtual environment
set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_ACTIVATE=%VENV_DIR%\Scripts\activate.bat"

if not exist "%VENV_PYTHON%" (
    echo [*] Setting up local Python virtual environment in .venv ...
    !PY_CMD! -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [WARNING] Could not create virtual environment in "%VENV_DIR%".
        echo Falling back to system Python...
        set "RUN_PYTHON=!PY_CMD!"
    ) else (
        set "RUN_PYTHON=%VENV_PYTHON%"
        echo [*] Installing dependencies from requirements.txt ...
        "%VENV_PYTHON%" -m pip install --upgrade pip
        "%VENV_PYTHON%" -m pip install -r "%~dp0requirements.txt"
    )
) else (
    set "RUN_PYTHON=%VENV_PYTHON%"
)

REM 3. Activate virtual environment if available
if exist "%VENV_ACTIVATE%" (
    call "%VENV_ACTIVATE%"
)

REM 4. Check core requirements
"%RUN_PYTHON%" -c "import flask, sqlalchemy" >nul 2>&1
if !errorlevel! neq 0 (
    echo [*] Installing required packages from requirements.txt ...
    "%RUN_PYTHON%" -m pip install -r "%~dp0requirements.txt"
)

REM 5. Open browser & launch server
echo.
echo =========================================================================
echo   The Matrix is launching at: http://127.0.0.1:5000
echo   Press Ctrl+C in this terminal window to stop the server.
echo =========================================================================
echo.

start "" "http://127.0.0.1:5000"

"%RUN_PYTHON%" "%~dp0backend\app.py"

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Server exited with an error.
    pause
)
