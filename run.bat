@echo off
setlocal

title Solar Predictor

:: ── Work from the script's own directory ─────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ============================================================
echo   Solar Predictor
echo ============================================================
echo.

:: ── First-time setup: venv doesn't exist yet ─────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [SETUP] First run - setting up environment (one-time only)...
    echo.

    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python is not installed or not on PATH.
        echo         Download it from https://www.python.org/downloads/
        echo         Make sure to tick "Add Python to PATH" during installation.
        pause
        exit /b 1
    )

    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )

    call ".venv\Scripts\activate.bat"

    echo [SETUP] Installing dependencies...
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        echo         Check your internet connection and try again.
        echo         Delete the .venv folder and re-run to try again.
        pause
        exit /b 1
    )

    echo [OK] Setup complete.
    echo.
) else (
    call ".venv\Scripts\activate.bat"
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo [LAUNCH] Starting Solar Predictor...
echo.

python main.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Solar Predictor exited with an error.
    echo         To reinstall dependencies, delete the .venv folder and re-run.
    pause
)

endlocal
