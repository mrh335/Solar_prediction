#!/usr/bin/env bash
# Solar Predictor launcher for Linux / macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  Solar Predictor"
echo "============================================================"
echo

VENV_DIR=".venv"

# ── First-time setup: venv doesn't exist yet ─────────────────────────────────
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[SETUP] First run - setting up environment (one-time only)..."
    echo

    # Locate Python 3.10+
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

    "$PYTHON" -m venv "$VENV_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    echo "[SETUP] Installing dependencies..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    echo "[OK] Setup complete."
    echo
else
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo "[LAUNCH] Starting Solar Predictor..."
echo

python main.py "$@"
