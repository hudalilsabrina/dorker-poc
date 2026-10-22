#!/usr/bin/env bash
# Wrapper: pakai venv kalau ada, kalau tidak pakai python3 sistem.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$DIR/.venv/bin/python" ]]; then
  exec "$DIR/.venv/bin/python" "$DIR/dorker.py" "$@"
fi
exec python3 "$DIR/dorker.py" "$@"
