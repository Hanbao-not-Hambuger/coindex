#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/dist/coindex-linux"

for required in "$ROOT/linux/app.py" "$ROOT/LICENSE" "$ROOT/Resources/Brand/AppIcon.png"; do
  if [[ ! -f "$required" ]]; then
    printf 'Missing Linux packaging input: %s\n' "$required" >&2
    exit 1
  fi
done

rm -rf "$APP"
mkdir -p "$APP/backend" "$APP/linux" "$APP/Resources/Brand" "$APP/scripts"
cp "$ROOT/backend/"*.py "$APP/backend/"
cp "$ROOT/linux/"*.py "$APP/linux/"
cp "$ROOT/scripts/install-linux.sh" "$ROOT/scripts/install-linux.py" "$APP/scripts/"
cp "$ROOT/LICENSE" "$APP/LICENSE"
cp "$ROOT/Resources/Brand/AppIcon.png" "$APP/Resources/Brand/AppIcon.png"
python3 "$ROOT/scripts/create-demo.py" "$APP/demo.json"
cat > "$APP/coindex" <<'LAUNCHER'
#!/bin/sh
set -eu
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON="${CODEX_TODO_PYTHON:-python3}"
exec "$PYTHON" "$APP_DIR/linux/app.py" "$@"
LAUNCHER
chmod 0755 "$APP/coindex"
chmod 0755 "$APP/scripts/install-linux.sh"
printf 'Built %s\n' "$APP"
