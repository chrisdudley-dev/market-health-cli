import json
import sqlite3
from pathlib import Path

import pytest

from market_health.alert_store import (
    add_alert,
    add_daily_digest,
    add_export,
    add_symbol_snapshot,
    add_system_event,
    count_rows,
    finish_run,
    init_db,
    start_run,
    table_names,
)


def test_init_db_creates_schema_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "market_health_alerts.v1.sqlite"

    init_db(db)
    init_db(db)

    assert db.exists()
    assert {
        "schema_migrations",
        "runs",
        "symbol_snapshots",
        "alerts",
        "system_events",
        "exports",
        "daily_digests",
    }.issubset(table_names(db))
    assert count_rows(db, "schema_migrations") == 1


def test_start_and_finish_run(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"

    run_id = start_run(
        db_path=db,
        mode="dry-run",
        trigger_name="manual",
        git_commit="abc123",
        started_at_utc="2026-04-30T14:30:00Z",
        details={"market_open": True},
    )
    finish_run(
        db_path=db,
        run_id=run_id,
        status="success",
        finished_at_utc="2026-04-30T14:31:00Z",
        details={"alerts": 0},
    )

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        """
        SELECT started_at_utc, finished_at_utc, status, mode, trigger_name,
               git_commit, details_json
        FROM runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    conn.close()

    assert row == (
        "2026-04-30T14:30:00Z",
        "2026-04-30T14:31:00Z",
        "success",
        "dry-run",
        "manual",
        "abc123",
        json.dumps({"alerts": 0}, sort_keys=True),
    )


def test_add_symbol_snapshot_and_alert(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    run_id = start_run(db_path=db, mode="test", trigger_name="timer")

    snapshot_id = add_symbol_snapshot(
        db_path=db,
        run_id=run_id,
        symbol="SPY",
        ts_utc="2026-04-30T15:00:00Z",
        current_score=72.5,
        blend_score=70.0,
        h1_score=66.0,
        h5_score=61.0,
        state="DMG",
        stop_price=505.25,
        buy_price=512.75,
        sup_atr=1.2,
        res_atr=0.8,
        last_price=510.0,
        source={"artifact": "market_health.ui.v1.json"},
    )
    alert_id = add_alert(
        db_path=db,
        run_id=run_id,
        alert_key="state:SPY:DMG",
        alert_type="state_change",
        severity="warning",
        symbol="SPY",
        title="SPY state changed",
        message="SPY changed to DMG.",
        ts_utc="2026-04-30T15:01:00Z",
        payload={"from": "clean", "to": "DMG"},
        delivery_status="dry-run",
    )

    assert snapshot_id == 1
    assert alert_id == 1
    assert count_rows(db, "symbol_snapshots") == 1
    assert count_rows(db, "alerts") == 1

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT symbol, state, source_json FROM symbol_snapshots WHERE id = ?",
        (snapshot_id,),
    ).fetchone()
    alert = conn.execute(
        "SELECT alert_key, delivery_status, payload_json FROM alerts WHERE id = ?",
        (alert_id,),
    ).fetchone()
    conn.close()

    assert row[0] == "SPY"
    assert row[1] == "DMG"
    assert json.loads(row[2]) == {"artifact": "market_health.ui.v1.json"}
    assert alert[0] == "state:SPY:DMG"
    assert alert[1] == "dry-run"
    assert json.loads(alert[2]) == {"from": "clean", "to": "DMG"}


def test_add_system_export_and_digest_rows(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    run_id = start_run(db_path=db, mode="dry-run", trigger_name="timer")

    system_event_id = add_system_event(
        db_path=db,
        run_id=run_id,
        event_type="refresh",
        severity="info",
        message="refresh-all completed",
        ts_utc="2026-04-30T15:10:00Z",
        payload={"status": "ok"},
    )
    export_id = add_export(
        db_path=db,
        run_id=run_id,
        export_type="snapshot_backup",
        target="local",
        status="success",
        path="/tmp/snapshot.json",
        ts_utc="2026-04-30T15:11:00Z",
        payload={"rows": 3},
    )
    digest_id = add_daily_digest(
        db_path=db,
        digest_date="2026-04-30",
        status="created",
        created_at_utc="2026-04-30T20:10:00Z",
        payload={"alerts": 2},
    )

    assert system_event_id == 1
    assert export_id == 1
    assert digest_id == 1
    assert count_rows(db, "system_events") == 1
    assert count_rows(db, "exports") == 1
    assert count_rows(db, "daily_digests") == 1


def test_count_rows_rejects_unknown_table(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    init_db(db)

    with pytest.raises(ValueError):
        count_rows(db, "not_a_table")
