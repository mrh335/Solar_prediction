@echo off
setlocal enabledelayedexpansion

title Solar Predictor

:: ── Find the script's own directory so it works from any CWD ─────────────────
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ============================================================
echo   Solar Predictor
echo ============================================================
echo.

:: ── Check Python is available ─────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo         Download it from https://www.python.org/downloads/
    echo         Make sure to tick "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% found.

:: ── Create virtual environment if it doesn't exist ───────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

:: ── Activate venv ─────────────────────────────────────────────────────────────
call ".venv\Scripts\activate.bat"

:: ── Install / update dependencies ─────────────────────────────────────────────
:: Only reinstall if requirements.txt is newer than the venv marker file
set "MARKER=.venv\.requirements_installed"
set "NEEDS_INSTALL=0"

if not exist "%MARKER%" set "NEEDS_INSTALL=1"
if exist "%MARKER%" (
    for %%F in (requirements.txt) do set "REQ_DATE=%%~tF"
    for %%F in ("%MARKER%") do set "MRK_DATE=%%~tF"
    if "!REQ_DATE!" GTR "!MRK_DATE!" set "NEEDS_INSTALL=1"
)

if "%NEEDS_INSTALL%"=="1" (
    echo.
    echo [SETUP] Installing / updating dependencies (this may take a minute)...
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        echo         Check your internet connection and try again.
        pause
        exit /b 1
    )
    echo. > "%MARKER%"
    echo [OK] Dependencies installed.
)

:: ── Launch the application ────────────────────────────────────────────────────
echo.
echo [LAUNCH] Starting Solar Predictor GUI...
echo.

python main.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Solar Predictor exited with an error.
    pause
)

endlocal
