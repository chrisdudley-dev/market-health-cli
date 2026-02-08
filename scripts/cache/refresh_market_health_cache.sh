#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.." || exit 1

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: .venv missing. Run: python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

./.venv/bin/python scripts/export_environment_v1.py "$@"
