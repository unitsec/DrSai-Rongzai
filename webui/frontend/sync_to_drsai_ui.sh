#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLIC_DIR="$SCRIPT_DIR/public"

if [[ ! -d "$PUBLIC_DIR" ]]; then
  echo "[error] frontend public directory not found: $PUBLIC_DIR"
  echo "Run 'yarn build' first."
  exit 1
fi

TARGET_DIR="${DRSAI_UI_STATIC_DIR:-}"

if [[ -z "$TARGET_DIR" ]]; then
  TARGET_DIR="$(python - <<'PY'
import importlib.util
from pathlib import Path

spec = importlib.util.find_spec('drsai_ui')
if spec is None or not spec.origin:
    raise SystemExit('')

pkg_dir = Path(spec.origin).resolve().parent
print(pkg_dir / 'ui_backend' / 'backend' / 'web' / 'ui')
PY
)"
fi

if [[ -z "$TARGET_DIR" ]]; then
  echo "[error] Cannot detect drsai_ui static directory."
  echo "Set DRSAI_UI_STATIC_DIR manually, e.g.:"
  echo "  DRSAI_UI_STATIC_DIR=/path/to/site-packages/drsai_ui/ui_backend/backend/web/ui yarn sync:ui"
  exit 1
fi

mkdir -p "$TARGET_DIR"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$PUBLIC_DIR/" "$TARGET_DIR/"
else
  rm -rf "$TARGET_DIR"/*
  cp -a "$PUBLIC_DIR"/. "$TARGET_DIR/"
fi

echo "Synced frontend static files to: $TARGET_DIR"
