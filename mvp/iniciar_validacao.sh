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
    echo "Python 3 not found. Install Python 3.10+ and the validation dependencies." >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    echo "Python 3.10+ is required for validation mode." >&2
    exit 1
fi

if ! "$PYTHON" -c 'from holidays import country_holidays' >/dev/null 2>&1; then
    echo "The 'holidays' dependency is missing for: $PYTHON" >&2
    echo "Install it with: \"$PYTHON\" -m pip install -r \"$MVP_DIR/requirements-validacao.txt\"" >&2
    exit 1
fi

export AUDITIA_BETA=0
export AUDITIA_IA_ENABLED=0
export AUDITIA_PORT=5000
export PYTHONUTF8=1
export PYTHONPATH="$MVP_DIR${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" app.py
