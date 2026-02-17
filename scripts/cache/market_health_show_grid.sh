#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/projects/market-health-cli"
PY="$REPO/.venv/bin/python"

# If venv python isn't there, fall back (but normally it should exist)
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

cd "$REPO"

# Normal interactive welcome should be a TTY; still, forcing helps if your environment is conservative
export MH_FORCE_COLOR="${MH_FORCE_COLOR:-1}"

# Default to 6 columns (matches your Pi grid example); allow override via env
GRID_COLS="${WELCOME_MARKET_HEALTH_GRID_COLS:-6}"

exec "$PY" -m market_health.market_ui --pi-grid --grid-cols "$GRID_COLS"
