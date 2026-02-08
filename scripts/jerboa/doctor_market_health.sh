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
STATE="${HOME}/.cache/jerboa/state/market_health_refresh_all.state.json"

ENV_JSON="${HOME}/.cache/jerboa/environment.v1.json"
SECT_JSON="${HOME}/.cache/jerboa/market_health.sectors.json"
POS_JSON="${HOME}/.cache/jerboa/positions.v1.json"

echo "== Repo root =="
echo "$REPO"
echo

echo "== Wrapper wiring (~/bin -> repo) =="
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

echo "== systemd unit files on disk =="
ls -1 "$UNITDIR"/jerboa-market-health-refresh-all.* 2>/dev/null || true
echo

echo "== Timer status + next trigger =="
systemctl --user is-enabled jerboa-market-health-refresh-all.timer 2>/dev/null || true
systemctl --user is-active  jerboa-market-health-refresh-all.timer 2>/dev/null || true
systemctl --user list-timers --all 2>/dev/null | grep -n 'jerboa-market-health-refresh-all' || true
echo

echo "== Recent service logs (last 120 lines) =="
journalctl --user -u jerboa-market-health-refresh-all.service -n 120 --no-pager 2>/dev/null || true
echo

echo "== Cache presence + timestamps =="
ls -lh --time-style=long-iso "$ENV_JSON" "$SECT_JSON" "$POS_JSON" 2>/dev/null || true
echo

echo "== Last refresh-all state (from state.json) =="
if [ -f "$STATE" ]; then
  python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.cache/jerboa/state/market_health_refresh_all.state.json")
try:
    d = json.load(open(p, "r", encoding="utf-8"))
except Exception as e:
    print("STATE: unreadable:", e)
    raise SystemExit(0)

ts = d.get("ts","?")
status = d.get("status","?")
reason = d.get("reason","?")
forced = d.get("forced", False)
chg = d.get("changed", {})
rc  = d.get("rc", {})
print(f"ts:      {ts}")
print(f"status:  {status}")
print(f"reason:  {reason}")
print(f"forced:  {forced}")
print(f"changed: market={chg.get('market','?')} positions={chg.get('positions','?')}")
print(f"rc:      market={rc.get('market','?')} positions={rc.get('positions','?')}")
PY
else
  echo "STATE: missing ($STATE)"
fi
echo

echo "== JSON sanity checks (parse) =="
python3 - <<'PY'
import json, os
paths = [
  os.path.expanduser("~/.cache/jerboa/environment.v1.json"),
  os.path.expanduser("~/.cache/jerboa/market_health.sectors.json"),
  os.path.expanduser("~/.cache/jerboa/positions.v1.json"),
  os.path.expanduser("~/.cache/jerboa/state/market_health_refresh_all.state.json"),
]
for p in paths:
    if not os.path.exists(p):
        print("MISSING:", p); continue
    try:
        json.load(open(p, "r", encoding="utf-8"))
        print("OK:", p)
    except Exception as e:
        print("BAD:", p, "->", e)
PY

echo
echo "DONE: doctor snapshot complete"
