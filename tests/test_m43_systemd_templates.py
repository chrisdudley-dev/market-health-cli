from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "scripts/jerboa/bin/jerboa-market-health-alert-run-once"
SERVICE = ROOT / "scripts/jerboa/systemd/user/jerboa-market-health-alert.service"
TIMER = ROOT / "scripts/jerboa/systemd/user/jerboa-market-health-alert.timer"


def test_alert_run_once_wrapper_exists_and_calls_python_runner() -> None:
    text = BIN.read_text(encoding="utf-8")

    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "JERBOA_MARKET_HEALTH_PYTHON" in text
    assert "$REPO/.venv/bin/python" in text
    assert '"$PYTHON" -m market_health.alert_runner' in text
    assert "--trigger-name systemd-timer" in text
    assert "JERBOA_MARKET_HEALTH_REPO" in text
    assert 'cd "$REPO"' in text
    assert "JERBOA_ALERT_DB" in text
    assert "JERBOA_MARKET_HEALTH_UI" in text
    assert "JERBOA_TELEGRAM_CONFIG" in text
    assert "JERBOA_ALERT_TELEGRAM_MODE" in text
    assert "JERBOA_ALERT_RUNNER_ARGS" in text
    assert '"${EXTRA_ARGS[@]}"' in text
    assert '"$@"' in text


def test_alert_service_is_user_oneshot_with_timeout_and_journald_identifier() -> None:
    text = SERVICE.read_text(encoding="utf-8")

    assert "Type=oneshot" in text
    assert "ExecStart=%h/bin/jerboa-market-health-alert-run-once" in text
    assert "TimeoutStartSec=10min" in text
    assert "SyslogIdentifier=jerboa-market-health-alert" in text
    assert "Nice=10" in text
    assert "NoNewPrivileges=yes" in text
    assert "PrivateTmp=yes" in text
    assert "ProtectSystem=strict" not in text
    assert "ProtectKernelTunables=yes" not in text
    assert "ProtectKernelModules=yes" not in text
    assert "ProtectControlGroups=yes" not in text


def test_alert_timer_runs_every_15_minutes_and_installs_to_timers_target() -> None:
    text = TIMER.read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* *:0/15:00" in text
    assert "Persistent=true" in text
    assert "Unit=jerboa-market-health-alert.service" in text
    assert "WantedBy=timers.target" in text
    assert "OnUnitActiveSec=15m" not in text


def test_service_and_timer_do_not_enable_themselves() -> None:
    service_text = SERVICE.read_text(encoding="utf-8")
    timer_text = TIMER.read_text(encoding="utf-8")

    assert "systemctl --user enable" not in service_text
    assert "systemctl --user enable" not in timer_text
    assert "systemctl --user start" not in service_text
    assert "systemctl --user start" not in timer_text
