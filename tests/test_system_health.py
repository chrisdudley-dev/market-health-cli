import json
import sqlite3
from pathlib import Path

from market_health.alert_store import add_system_event, finish_run, start_run
from market_health.system_health import (
    collect_system_health_alerts,
    detect_no_recent_successful_run,
    detect_recent_system_failures,
    detect_ui_artifact_health,
    record_system_health_alert,
)


def _write_ui(path: Path, *, asof: str = "2026-05-01T15:00:00Z") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "jerboa.market_health.ui.v1",
                "asof": asof,
                "data": {"positions": {"positions": []}, "sectors": []},
            }
        ),
        encoding="utf-8",
    )


def test_detects_missing_ui_artifact(tmp_path: Path) -> None:
    alerts = detect_ui_artifact_health(
        ui_path=tmp_path / "missing.json",
        now_utc="2026-05-01T15:00:00Z",
    )

    assert len(alerts) == 1
    assert alerts[0].alert_key == "system_health:ui_artifact_missing"
    assert alerts[0].severity == "critical"


def test_detects_stale_ui_artifact(tmp_path: Path) -> None:
    ui = tmp_path / "market_health.ui.v1.json"
    _write_ui(ui, asof="2026-05-01T14:00:00Z")

    alerts = detect_ui_artifact_health(
        ui_path=ui,
        now_utc="2026-05-01T15:00:00Z",
        stale_after_minutes=30,
    )

    assert len(alerts) == 1
    assert alerts[0].alert_key == "system_health:ui_artifact_stale"
    assert alerts[0].severity == "warning"
    assert alerts[0].payload["age_minutes"] == 60.0


def test_fresh_ui_artifact_has_no_alert(tmp_path: Path) -> None:
    ui = tmp_path / "market_health.ui.v1.json"
    _write_ui(ui, asof="2026-05-01T14:45:00Z")

    alerts = detect_ui_artifact_health(
        ui_path=ui,
        now_utc="2026-05-01T15:00:00Z",
        stale_after_minutes=30,
    )

    assert alerts == []


def test_detects_no_successful_run(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"

    alerts = detect_no_recent_successful_run(
        db_path=db,
        now_utc="2026-05-01T15:00:00Z",
    )

    assert len(alerts) == 1
    assert alerts[0].alert_key == "system_health:no_successful_run"


def test_detects_no_recent_successful_run(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    run_id = start_run(
        db_path=db,
        mode="dry-run",
        trigger_name="manual",
        started_at_utc="2026-05-01T13:00:00Z",
    )
    finish_run(
        db_path=db,
        run_id=run_id,
        status="success",
        finished_at_utc="2026-05-01T13:01:00Z",
    )

    alerts = detect_no_recent_successful_run(
        db_path=db,
        now_utc="2026-05-01T15:00:00Z",
        max_age_minutes=60,
    )

    assert len(alerts) == 1
    assert alerts[0].alert_key == "system_health:no_recent_successful_run"
    assert alerts[0].payload["age_minutes"] == 119.0


def test_recent_successful_run_has_no_alert(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    run_id = start_run(
        db_path=db,
        mode="dry-run",
        trigger_name="manual",
        started_at_utc="2026-05-01T14:55:00Z",
    )
    finish_run(
        db_path=db,
        run_id=run_id,
        status="success",
        finished_at_utc="2026-05-01T14:56:00Z",
    )

    alerts = detect_no_recent_successful_run(
        db_path=db,
        now_utc="2026-05-01T15:00:00Z",
        max_age_minutes=60,
    )

    assert alerts == []


def test_detects_recent_system_failure_event(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"

    add_system_event(
        db_path=db,
        event_type="refresh_failed",
        severity="error",
        message="refresh failed with exit code 7",
        ts_utc="2026-05-01T14:50:00Z",
        payload={"exit_code": 7},
    )

    alerts = detect_recent_system_failures(
        db_path=db,
        now_utc="2026-05-01T15:00:00Z",
        lookback_minutes=60,
    )

    assert len(alerts) == 1
    assert alerts[0].alert_key == "system_health:recent_refresh_failed"
    assert alerts[0].severity == "critical"
    assert alerts[0].payload["payload"] == {"exit_code": 7}


def test_ignores_old_system_failure_event(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"

    add_system_event(
        db_path=db,
        event_type="refresh_failed",
        severity="error",
        message="old refresh failure",
        ts_utc="2026-05-01T12:00:00Z",
    )

    alerts = detect_recent_system_failures(
        db_path=db,
        now_utc="2026-05-01T15:00:00Z",
        lookback_minutes=60,
    )

    assert alerts == []


def test_collect_system_health_alerts_combines_checks(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"
    _write_ui(ui, asof="2026-05-01T14:00:00Z")

    add_system_event(
        db_path=db,
        event_type="telegram_send_failed",
        severity="error",
        message="network down",
        ts_utc="2026-05-01T14:55:00Z",
    )

    alerts = collect_system_health_alerts(
        db_path=db,
        ui_path=ui,
        now_utc="2026-05-01T15:00:00Z",
        artifact_stale_after_minutes=30,
        successful_run_max_age_minutes=60,
        failure_lookback_minutes=60,
    )

    assert [a.alert_key for a in alerts] == [
        "system_health:ui_artifact_stale",
        "system_health:no_successful_run",
        "system_health:recent_telegram_send_failed",
    ]


def test_record_system_health_alert_writes_system_event(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    alert = detect_ui_artifact_health(
        ui_path=tmp_path / "missing.json",
        now_utc="2026-05-01T15:00:00Z",
    )[0]

    event_id = record_system_health_alert(
        db_path=db,
        candidate=alert,
        ts_utc="2026-05-01T15:00:00Z",
    )

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT id, event_type, severity, message, payload_json FROM system_events"
    ).fetchone()
    conn.close()

    assert event_id == 1
    assert row[0] == 1
    assert row[1] == "system_health_ui_artifact_missing"
    assert row[2] == "critical"
    assert "missing" in row[3]
    assert json.loads(row[4])["path"].endswith("missing.json")
