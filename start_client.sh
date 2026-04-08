#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_EXE=""
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  PYTHON_EXE="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python)"
else
  echo "Python not found. Please install Python 3.11+ or create .venv first." >&2
  exit 1
fi

"$PYTHON_EXE" zrok_client.py start "$@"
