#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
REPO="$(
  cd "$SCRIPT_DIR" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || true
)"
if [ -z "${REPO:-}" ]; then
  REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

BIN="${HOME}/bin"
UNITDIR="${HOME}/.config/systemd/user"
mkdir -p "$BIN" "$UNITDIR"

echo "== Repo root =="
echo "$REPO"
echo

echo "== Install symlinks -> repo-managed wrappers =="
for name in \
  jerboa-market-health-refresh \
  jerboa-market-health-positions-refresh \
  jerboa-market-health-refresh-all \
  jerboa-market-health-ui-export \
  jerboa-market-health-status \
  jerboa-market-health-alert
do
  src="$REPO/scripts/jerboa/bin/$name"
  dst="$BIN/$name"
  if [ ! -x "$src" ]; then
    echo "ERROR: missing executable wrapper: $src"
    exit 1
  fi
  ln -sf "$src" "$dst"
done
hash -r

ln -snf "$REPO/scripts/jerboa/update_market_health.sh" "$HOME/bin/jerboa-market-health-update"

echo "== Install systemd units -> ~/.config/systemd/user (copy from repo) =="
install -m 0644 "$REPO/scripts/jerboa/systemd/user/jerboa-market-health-refresh-all.service" \
               "$UNITDIR/jerboa-market-health-refresh-all.service"
install -m 0644 "$REPO/scripts/jerboa/systemd/user/jerboa-market-health-refresh-all.timer" \
               "$UNITDIR/jerboa-market-health-refresh-all.timer"
install -m 0644 "$REPO/scripts/jerboa/systemd/user/jerboa-market-health-refresh-all-failure.service" \
               "$UNITDIR/jerboa-market-health-refresh-all-failure.service"

echo "== Reload + enable timer =="
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user enable jerboa-market-health-refresh-all.timer
  systemctl --user restart jerboa-market-health-refresh-all.timer || systemctl --user start jerboa-market-health-refresh-all.timer

  systemctl --user is-enabled jerboa-market-health-refresh-all.timer
  systemctl --user is-active  jerboa-market-health-refresh-all.timer
  systemctl --user list-timers --all | grep -n 'jerboa-market-health-refresh-all' || true
else
  echo "WARN: systemctl not available; skipped user timer reload/restart"
fi

echo "== One-shot transient test (forced) =="
if command -v systemd-run >/dev/null 2>&1; then
  systemd-run --user --unit=jerboa-mh-install-probe --wait --collect \
    "$HOME/bin/jerboa-market-health-refresh-all" --force >/dev/null

  echo "== Probe logs (last 120 lines) =="
  journalctl --user -u jerboa-mh-install-probe -n 120 --no-pager || true
else
  echo "WARN: systemd-run not available; running direct forced refresh instead"
  "$HOME/bin/jerboa-market-health-refresh-all" --force >/dev/null || true
fi

echo "== Status line (for banner) =="
"$HOME/bin/jerboa-market-health-status" || true

echo "DONE: install complete"


# Enable localhost UI server
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user enable --now jerboa-market-health-ui.service >/dev/null 2>&1 || true
else
  echo "WARN: systemctl not available; skipped UI service enable"
fi
