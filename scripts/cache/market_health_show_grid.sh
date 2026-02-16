#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.." || exit 1

JSON="${1:-$HOME/.cache/jerboa/environment.v1.json}"

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: .venv missing. Run: python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

if [ ! -f "$JSON" ]; then
  echo "ERROR: missing $JSON (run refresh first)" >&2
  exit 1
fi

exec ./.venv/bin/python market_ui.py --json "$JSON" --pi-grid --grid-cols 0
