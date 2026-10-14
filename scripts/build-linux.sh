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

if [[ -e "$APP" || -L "$APP" ]]; then
  if [[ ! -d "$APP" || -L "$APP" || ! -f "$APP/coindex" ]] || \
     ! grep -Fxq '# Managed by coindex build-linux.sh' "$APP/coindex"; then
    printf 'Refusing to replace an existing unrecognized path: %s\n' "$APP" >&2
    exit 1
  fi
  rm -rf "$APP"
fi
mkdir -p "$APP/backend" "$APP/linux" "$APP/Resources/Brand" "$APP/scripts"
cp "$ROOT/backend/"*.py "$APP/backend/"
cp "$ROOT/linux/"*.py "$APP/linux/"
cp "$ROOT/scripts/install-linux.sh" "$ROOT/scripts/install-linux.py" "$APP/scripts/"
cp "$ROOT/LICENSE" "$APP/LICENSE"
cp "$ROOT/Resources/Brand/AppIcon.png" "$APP/Resources/Brand/AppIcon.png"
python3 "$ROOT/scripts/create-demo.py" "$APP/demo.json"
cat > "$APP/coindex" <<'LAUNCHER'
#!/bin/sh
# Managed by coindex build-linux.sh
set -eu
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON="${CODEX_TODO_PYTHON:-python3}"
exec "$PYTHON" "$APP_DIR/linux/app.py" "$@"
LAUNCHER
chmod 0755 "$APP/coindex"
chmod 0755 "$APP/scripts/install-linux.sh"
printf 'Built %s\n' "$APP"
