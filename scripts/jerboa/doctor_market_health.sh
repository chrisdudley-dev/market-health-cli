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
ALERTDIR="${HOME}/.cache/jerboa/alerts"

ENV_JSON="${HOME}/.cache/jerboa/environment.v1.json"
SECT_JSON="${HOME}/.cache/jerboa/market_health.sectors.json"
POS_JSON="${HOME}/.cache/jerboa/positions.v1.json"
FORECAST_JSON="${HOME}/.cache/jerboa/forecast_scores.v1.json"
REC_JSON="${HOME}/.cache/jerboa/recommendations.v1.json"
UI_JSON="${HOME}/.cache/jerboa/market_health.ui.v1.json"
ALERT_DB="${HOME}/.cache/jerboa/market_health_alerts.v1.sqlite"
SCHWAB_CONFIG="${HOME}/.config/jerboa/schwab_oauth.json"
SCHWAB_TOKEN="${HOME}/.cache/jerboa/schwab.token.json"

PYTHON="${JERBOA_MARKET_HEALTH_PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x "$REPO/.venv/bin/python" ]; then
    PYTHON="$REPO/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

echo "== Repo root =="
echo "$REPO"

echo
echo "== Status line (banner-friendly) =="
if [ -x "$BIN/jerboa-market-health-status" ]; then
  "$BIN/jerboa-market-health-status" || true
else
  echo "MISSING: $BIN/jerboa-market-health-status"
fi

echo
echo "== Wrapper wiring (~/bin -> repo) =="
for name in \
  jerboa-market-health-refresh \
  jerboa-market-health-positions-refresh \
  jerboa-market-health-refresh-all \
  jerboa-market-health-alert \
  jerboa-market-health-status
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
ls -1 "$UNITDIR"/jerboa-market-health-refresh-all*.service "$UNITDIR"/jerboa-market-health-refresh-all.timer 2>/dev/null || true

echo
echo "== Timer status + next trigger =="
systemctl --user is-enabled jerboa-market-health-refresh-all.timer 2>/dev/null || true
systemctl --user is-active  jerboa-market-health-refresh-all.timer 2>/dev/null || true
systemctl --user list-timers --all 2>/dev/null | grep -n 'jerboa-market-health-refresh-all' || true

echo
echo "== Unit properties (service) =="
systemctl --user show jerboa-market-health-refresh-all.service -p ExecStart -p TimeoutStartUSec -p OnFailure -p Nice -p PrivateTmp -p ProtectSystem --no-pager 2>/dev/null || true

echo
echo "== Recent service logs (last 80 lines) =="
journalctl --user -u jerboa-market-health-refresh-all.service -n 80 --no-pager 2>/dev/null || true

echo
echo "== Cache presence + timestamps =="
ls -lh --time-style=long-iso \
  "$ENV_JSON" \
  "$SECT_JSON" \
  "$POS_JSON" \
  "$FORECAST_JSON" \
  "$REC_JSON" \
  "$UI_JSON" \
  "$ALERT_DB" \
  2>/dev/null || true

echo
echo "== Last refresh-all state (state.json) =="
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
chg = d.get("changed", {}) or {}
rc  = d.get("rc", {}) or {}
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
echo "== Latest alert bundle (tail) =="
latest="$(ls -1t "$ALERTDIR"/market-health-failure-*.txt 2>/dev/null | head -1 || true)"
if [ -n "${latest:-}" ]; then
  echo "latest: $latest"
  echo "--- tail -n 40 ---"
  tail -n 40 "$latest" || true
else
  echo "none yet in $ALERTDIR"
fi


echo
echo "== M43 alert status =="
if [ -x "$BIN/mh_alert_status" ]; then
  "$BIN/mh_alert_status" || true
else
  "$PYTHON" -m market_health.alert_status --db "$ALERT_DB" --repo "$REPO" || true
fi

echo
echo "== M43 alert timer status =="
systemctl --user is-enabled jerboa-market-health-alert.timer 2>/dev/null || true
systemctl --user is-active  jerboa-market-health-alert.timer 2>/dev/null || true
systemctl --user list-timers --all 2>/dev/null | grep -n 'jerboa-market-health-alert' || true

echo
echo "== Schwab OAuth status =="
schwab_status="$("$PYTHON" "$REPO/scripts/schwab_oauth_cli.py" --status 2>/dev/null || true)"
if [ -n "$schwab_status" ]; then
  printf '%s\n' "$schwab_status"
else
  echo "Schwab status unavailable"
fi

echo
echo "== Operator next action =="
alert_timer_enabled="$(systemctl --user is-enabled jerboa-market-health-alert.timer 2>/dev/null || true)"
alert_timer_active="$(systemctl --user is-active jerboa-market-health-alert.timer 2>/dev/null || true)"
schwab_missing="$(printf '%s\n' "$schwab_status" | awk -F= '$1=="config_missing"{print $2; exit}')"
token_exists="$(printf '%s\n' "$schwab_status" | awk -F= '$1=="token_exists"{print $2; exit}')"

printed_next_action=0

if [ -n "$schwab_missing" ] || [ "$token_exists" = "False" ]; then
  echo "- Schwab live positions are not ready: complete local config/token setup, or continue using CSV/sample positions."
  echo "  config: $SCHWAB_CONFIG"
  echo "  token:  $SCHWAB_TOKEN"
  printed_next_action=1
fi

if [ "$alert_timer_enabled" != "enabled" ] || [ "$alert_timer_active" != "active" ]; then
  echo "- M43 alert timer is not active. Enable it only after Telegram mode and positions source are ready."
  printed_next_action=1
fi

if [ ! -f "$UI_JSON" ]; then
  echo "- UI artifact is missing. Run jerboa-market-health-refresh-all."
  printed_next_action=1
fi

if [ "$printed_next_action" -eq 0 ]; then
  echo "- No blocking readiness issue detected by this doctor snapshot."
fi


echo
echo "DONE: doctor snapshot complete"
