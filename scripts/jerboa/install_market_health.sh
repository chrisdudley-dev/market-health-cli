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

echo "== Install systemd units -> ~/.config/systemd/user (copy from repo) =="
install -m 0644 "$REPO/scripts/jerboa/systemd/user/jerboa-market-health-refresh-all.service" \
               "$UNITDIR/jerboa-market-health-refresh-all.service"
install -m 0644 "$REPO/scripts/jerboa/systemd/user/jerboa-market-health-refresh-all.timer" \
               "$UNITDIR/jerboa-market-health-refresh-all.timer"
install -m 0644 "$REPO/scripts/jerboa/systemd/user/jerboa-market-health-refresh-all-failure.service" \
               "$UNITDIR/jerboa-market-health-refresh-all-failure.service"

echo "== Reload + enable timer =="
systemctl --user daemon-reload
systemctl --user enable --now jerboa-market-health-refresh-all.timer

echo "== Show timer status + next trigger =="
systemctl --user is-enabled jerboa-market-health-refresh-all.timer
systemctl --user is-active  jerboa-market-health-refresh-all.timer
systemctl --user list-timers --all | grep -n 'jerboa-market-health-refresh-all' || true

echo "== One-shot transient test (forced) =="
systemd-run --user --unit=jerboa-mh-install-probe --wait --collect \
  "$HOME/bin/jerboa-market-health-refresh-all" --force >/dev/null

echo "== Probe logs (last 120 lines) =="
journalctl --user -u jerboa-mh-install-probe -n 120 --no-pager || true

echo "== Status line (for banner) =="
"$HOME/bin/jerboa-market-health-status" || true

echo "DONE: install complete"


# Enable localhost UI server
systemctl --user enable --now jerboa-market-health-ui.service >/dev/null 2>&1 || true
