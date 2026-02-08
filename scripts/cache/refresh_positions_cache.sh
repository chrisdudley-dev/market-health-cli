#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.." || exit 1

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: .venv missing in repo" >&2
  exit 1
fi

exec ./.venv/bin/python scripts/import_positions_tos_csv.py "$@"
