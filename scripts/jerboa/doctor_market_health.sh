#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(
  cd "$SCRIPT_DIR" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || true
)"
if [ -z "${REPO:-}" ]; then
  REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

BIN="${HOME}/bin"
UNITDIR="${HOME}/.config/systemd/user"

echo "== Repo root =="
echo "$REPO"
echo

echo "== Wrapper wiring (should point into repo) =="
for name in \
  jerboa-market-health-refresh \
  jerboa-market-health-positions-refresh \
  jerboa-market-health-refresh-all
do
  p="$BIN/$name"
  if [ ! -e "$p" ]; then
    echo "MISSING: $p"
    continue
  fi
  target="$(readlink -f "$p" 2>/dev/null || true)"
  echo "- $name: $p -> ${target:-UNKNOWN}"
done
echo

echo "== systemd units on disk =="
ls -1 "$UNITDIR"/jerboa-market-health-refresh-all.* 2>/dev/null || true
echo

echo "== Timer status + next trigger =="
systemctl --user status jerboa-market-health-refresh-all.timer --no-pager || true
echo
systemctl --user list-timers --all | grep -n 'jerboa-market-health-refresh-all' || true
echo

echo "== Recent service logs (last 120 lines) =="
journalctl --user -u jerboa-market-health-refresh-all.service -n 120 --no-pager || true
echo

echo "== Cache presence + timestamps =="
ls -lh --time-style=long-iso \
  ~/.cache/jerboa/environment.v1.json \
  ~/.cache/jerboa/market_health.sectors.json \
  ~/.cache/jerboa/positions.v1.json
echo

echo "== JSON sanity check (parse) =="
python3 - <<'PY'
import json, os
paths = [
  os.path.expanduser("~/.cache/jerboa/environment.v1.json"),
  os.path.expanduser("~/.cache/jerboa/market_health.sectors.json"),
  os.path.expanduser("~/.cache/jerboa/positions.v1.json"),
]
for p in paths:
    with open(p, "r", encoding="utf-8") as f:
        json.load(f)
    print("OK:", p)
PY

echo "DONE: doctor clean"
