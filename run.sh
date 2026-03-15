#!/usr/bin/env bash
# Solar Predictor launcher for Linux / macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  Solar Predictor"
echo "============================================================"
echo

# ── Locate Python 3.10+ ───────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo False)
        if [ "$ver" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.10 or newer is required but was not found."
    echo "        Install it via your package manager or from https://python.org"
    exit 1
fi

echo "[OK] Using $($PYTHON --version)"

# ── Virtual environment ───────────────────────────────────────────────────────
VENV_DIR=".venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo
    echo "[SETUP] Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    echo "[OK] Virtual environment created."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Install / update dependencies ────────────────────────────────────────────
MARKER="$VENV_DIR/.requirements_installed"
NEEDS_INSTALL=0

if [ ! -f "$MARKER" ]; then
    NEEDS_INSTALL=1
elif [ requirements.txt -nt "$MARKER" ]; then
    NEEDS_INSTALL=1
fi

if [ "$NEEDS_INSTALL" -eq 1 ]; then
    echo
    echo "[SETUP] Installing / updating dependencies..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    touch "$MARKER"
    echo "[OK] Dependencies installed."
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo
echo "[LAUNCH] Starting Solar Predictor GUI..."
echo

python main.py "$@"
