import sqlite3
from pathlib import Path

from market_health.alert_status import (
    CommandResult,
    build_alert_status,
    format_status_text,
    main,
)
from market_health.alert_store import (
    add_alert,
    add_system_event,
    add_symbol_snapshot,
    finish_run,
    start_run,
)


def _runner(cmd):
    text = " ".join(cmd)
    if "rev-parse" in text:
        return CommandResult(0, "abc123")
    if "cat jerboa-market-health-alert.service" in text:
        return CommandResult(0, "[Service]")
    if "cat jerboa-market-health-alert.timer" in text:
        return CommandResult(0, "[Timer]")
    if "is-enabled jerboa-market-health-alert.timer" in text:
        return CommandResult(0, "enabled")
    if "is-enabled jerboa-market-health-alert.service" in text:
        return CommandResult(1, "static")
    if "is-active jerboa-market-health-alert.timer" in text:
        return CommandResult(0, "active")
    if "is-active jerboa-market-health-alert.service" in text:
        return CommandResult(3, "inactive")
    return CommandResult(1, "")


def test_build_alert_status_handles_missing_db(tmp_path: Path) -> None:
    status = build_alert_status(
        db_path=tmp_path / "missing.sqlite",
        repo_path=tmp_path,
        runner=_runner,
    )

    assert status["database"]["db_exists"] is False
    assert status["database"]["db_size_bytes"] == 0
    assert status["database"]["last_run"] is None
    assert status["git_commit"] == "abc123"
    assert status["service"]["installed"] is True
    assert status["timer"]["enabled"] == "enabled"


def test_build_alert_status_reads_sqlite_state(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    run_id = start_run(
        db_path=db,
        mode="dry-run",
        trigger_name="manual",
        started_at_utc="2026-05-01T15:00:00Z",
    )
    add_symbol_snapshot(
        db_path=db,
        run_id=run_id,
        symbol="SPY",
        ts_utc="2026-05-01T15:01:00Z",
        h1_score=66,
        h5_score=61,
    )
    add_alert(
        db_path=db,
        run_id=run_id,
        alert_key="position_state:SPY:clean->DMG",
        alert_type="position_state_changed",
        severity="warning",
        title="SPY state changed",
        message="SPY changed.",
        ts_utc="2026-05-01T15:02:00Z",
        delivery_status="dry-run",
    )
    add_system_event(
        db_path=db,
        run_id=run_id,
        event_type="refresh_failed",
        severity="error",
        message="refresh failed",
        ts_utc="2026-05-01T15:03:00Z",
    )
    finish_run(
        db_path=db,
        run_id=run_id,
        status="success",
        finished_at_utc="2026-05-01T15:04:00Z",
    )

    status = build_alert_status(db_path=db, repo_path=tmp_path, runner=_runner)

    assert status["database"]["db_exists"] is True
    assert status["database"]["last_run"]["status"] == "success"
    assert status["database"]["last_successful_run"]["id"] == run_id
    assert status["database"]["last_failed_run"] == {}
    assert status["database"]["latest_positions_timestamp"] == "2026-05-01T15:01:00Z"
    assert status["database"]["latest_forecast_timestamp"] == "2026-05-01T15:01:00Z"
    assert status["database"]["latest_telegram_alert"]["delivery_status"] == "dry-run"
    assert (
        status["database"]["latest_system_health_event"]["event_type"]
        == "refresh_failed"
    )


def test_build_alert_status_reads_last_failed_run(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    run_id = start_run(
        db_path=db,
        mode="disabled",
        trigger_name="manual",
        started_at_utc="2026-05-01T15:00:00Z",
    )
    finish_run(
        db_path=db,
        run_id=run_id,
        status="failed",
        finished_at_utc="2026-05-01T15:01:00Z",
        error_text="refresh failed",
    )

    status = build_alert_status(db_path=db, repo_path=tmp_path, runner=_runner)

    assert status["database"]["last_failed_run"]["id"] == run_id
    assert status["database"]["last_failed_run"]["error_text"] == "refresh failed"


def test_status_text_contains_operator_fields(tmp_path: Path) -> None:
    status = build_alert_status(
        db_path=tmp_path / "missing.sqlite",
        repo_path=tmp_path,
        runner=_runner,
    )

    text = format_status_text(status)

    assert "m43-alert-status:" in text
    assert "service:" in text
    assert "timer:" in text
    assert "database:" in text
    assert "git_commit:" in text
    assert "last_run:" in text
    assert "latest_telegram_alert:" in text
    assert "latest_system_health_event:" in text


def test_systemd_unavailable_is_graceful(tmp_path: Path) -> None:
    def runner(_cmd):
        return CommandResult(127, "", "systemctl not found")

    status = build_alert_status(
        db_path=tmp_path / "missing.sqlite",
        repo_path=tmp_path,
        runner=runner,
    )

    assert status["service"]["systemd_available"] is False
    assert status["timer"]["systemd_available"] is False


def test_main_prints_json_status_for_missing_db(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "--db",
            str(tmp_path / "missing.sqlite"),
            "--repo",
            str(tmp_path),
            "--json",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert '"database"' in out
    assert '"db_exists": false' in out


def test_wrapper_script_exists_and_calls_module() -> None:
    p = Path("scripts/jerboa/bin/mh_alert_status")
    text = p.read_text(encoding="utf-8")

    assert text.startswith("#!/usr/bin/env bash")
    assert "python -m market_health.alert_status" in text
    assert "JERBOA_ALERT_DB" in text
    assert "JERBOA_MARKET_HEALTH_REPO" in text


def test_status_does_not_create_missing_db(tmp_path: Path) -> None:
    db = tmp_path / "missing.sqlite"

    build_alert_status(db_path=db, repo_path=tmp_path, runner=_runner)

    assert not db.exists()


def test_sqlite_status_handles_existing_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(str(db)).close()

    status = build_alert_status(db_path=db, repo_path=tmp_path, runner=_runner)

    assert status["database"]["db_exists"] is True
    assert status["database"]["last_run"] == {}
