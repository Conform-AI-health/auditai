#!/usr/bin/env bash
set -euo pipefail

MVP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$MVP_DIR")"
cd "$MVP_DIR"

PYTHON="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
    echo "Python 3 not found. Install Python 3.10+ and the project dependencies." >&2
    exit 1
fi

export AUDITIA_BETA=1
export AUDITIA_PORT=5000
export PYTHONUTF8=1
export PYTHONPATH="$MVP_DIR${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" app.py
