#!/usr/bin/env bash
set -Eeuo pipefail

# Repo root from this file location
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PY="./.venv/bin/python"
if [ ! -x "$PY" ]; then PY="python3"; fi

SCHWAB_JSON=""
OUT=""

# Preserve args for ToS importer
PASSTHRU=()

while [ $# -gt 0 ]; do
  case "$1" in
    --schwab-json)
      SCHWAB_JSON="${2:-}"; shift 2;;
    --out)
      OUT="${2:-}"; PASSTHRU+=("$1" "${2:-}"); shift 2;;
    *)
      PASSTHRU+=("$1"); shift;;
  esac
done

if [ -n "$SCHWAB_JSON" ]; then
  if [ -z "$OUT" ]; then OUT="${HOME}/.cache/jerboa/positions.v1.json"; fi
  exec "$PY" scripts/import_positions_schwab_json.py --in "$SCHWAB_JSON" --out "$OUT"
fi

exec "$PY" scripts/import_positions_tos_csv.py "${PASSTHRU[@]}"
