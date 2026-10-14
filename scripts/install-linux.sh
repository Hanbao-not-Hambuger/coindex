#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${CODEX_TODO_PYTHON:-python3}"
exec "$PYTHON" "$SCRIPT_DIR/install-linux.py" "$@"
