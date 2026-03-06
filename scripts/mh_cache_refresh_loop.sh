#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export HOME=/root
VENV_PY="/root/market-health-cli/.venv/bin/python"

CACHE_DIR="${HOME}/.cache/jerboa"
LOCKDIR="${CACHE_DIR}/locks"
mkdir -p "$CACHE_DIR" "$LOCKDIR"
chmod 700 "$CACHE_DIR" 2>/dev/null || true

LOCK="${LOCKDIR}/mh_cache_refresh_loop.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[skip] refresh loop already running (lock busy)"
  exit 0
fi

INTERVAL="${MH_REFRESH_SECONDS:-900}"   # 15 minutes
ONCE=0
FORCE=0
NO_SCHWAB=0

while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1; shift ;;
    --force) FORCE=1; shift ;;
    --no-schwab) NO_SCHWAB=1; shift ;;
    --interval) INTERVAL="${2:-900}"; shift 2 ;;
    *) echo "ERR: unknown arg $1" >&2; exit 2 ;;
  esac
done

LAST_EPOCH_FILE="${CACHE_DIR}/refresh.last_epoch"
LOG="${CACHE_DIR}/mh_refresh_loop.nohup.log"
PIDFILE="${CACHE_DIR}/mh_refresh_loop.pid"

is_market_open() {
  "$VENV_PY" - <<'PY'
from datetime import datetime, time
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("America/New_York"))
if now.weekday() >= 5:
    raise SystemExit(1)
t = now.time()
raise SystemExit(0 if time(9,30) <= t <= time(16,0) else 1)
PY
}

read_last() { [ -f "$LAST_EPOCH_FILE" ] && cat "$LAST_EPOCH_FILE" 2>/dev/null || echo 0; }
write_last() { printf "%s\n" "$1" > "$LAST_EPOCH_FILE"; }

do_refresh() {
  echo "[$(date -Is)] refresh:start no_schwab=${NO_SCHWAB}" >> "$LOG"

  # 1) Schwab pull -> positions cache (ONLY during market hours unless --force)
  if [ "$NO_SCHWAB" -eq 0 ]; then
    scripts/schwab_live_refresh.sh >> "$LOG" 2>&1 || echo "[$(date -Is)] WARN: schwab_live_refresh failed" >> "$LOG"
  else
    echo "[$(date -Is)] refresh:skip_schwab" >> "$LOG"
  fi

  # 2) Derived caches + UI contract (does not hit Schwab)
  scripts/jerboa/bin/jerboa-market-health-refresh-all >> "$LOG" 2>&1 || echo "[$(date -Is)] WARN: refresh-all failed" >> "$LOG"

  # SYNC_REC_ASOF_TO_UI_ASOF_V1 (no network): keep rec asof coherent with UI snapshot asof
  "$VENV_PY" - <<'PYSYNC' >> "$LOG" 2>&1 || true
import json
from pathlib import Path
ui_p = Path("/root/.cache/jerboa/market_health.ui.v1.json")
rec_p = Path("/root/.cache/jerboa/recommendations.v1.json")
if ui_p.exists() and rec_p.exists():
    ui = json.loads(ui_p.read_text(encoding="utf-8"))
    asof = ui.get("asof")
    if asof:
        rec = json.loads(rec_p.read_text(encoding="utf-8"))
        rec["asof"] = asof
        if isinstance(rec.get("recommendation"), dict):
            rec["recommendation"]["asof"] = asof
        if "generated_at" in rec:
            rec["generated_at"] = asof
        rec_p.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("synced recommendations.asof to UI asof")
PYSYNC

  echo "[$(date -Is)] refresh:done" >> "$LOG"
}

loop_once() {
  local now last
  now="$(date +%s)"
  last="$(read_last)"

  if [ "$FORCE" -eq 1 ]; then
    do_refresh
    write_last "$now"
    return 0
  fi

  if ! is_market_open; then
    echo "[$(date -Is)] market-closed:skip" >> "$LOG"
    return 2
  fi

  if [ $((now - last)) -lt "$INTERVAL" ]; then
    echo "[$(date -Is)] cooldown:skip (age=$((now-last))s < ${INTERVAL}s)" >> "$LOG"
    return 0
  fi

  do_refresh
  write_last "$now"
  return 0
}

echo $$ > "$PIDFILE" 2>/dev/null || true

if [ "$ONCE" -eq 1 ]; then
  loop_once
  exit 0
fi

echo "[$(date -Is)] loop:start interval=${INTERVAL}s" >> "$LOG"
while true; do
  if loop_once; then
    sleep 60
  else
    sleep 600
  fi
done
