import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

from market_health.alert_runner import AlertRunnerConfig, main, run_once_alert_service
from market_health.alert_store import count_rows


def _write_ui(
    path: Path,
    *,
    state: str = "clean",
    c: float = 72.0,
    h1: float = 69.0,
    h5: float = 68.0,
    blend: float = 70.0,
) -> None:
    doc = {
        "schema": "jerboa.market_health.ui.v1",
        "asof": "2026-05-01T15:00:00Z",
        "data": {
            "positions": {
                "schema": "positions.v1",
                "positions": [{"symbol": "SPY", "last_price": 510.0}],
            },
            "sectors": [
                {
                    "symbol": "SPY",
                    "C": c,
                    "Blend": blend,
                    "H1": h1,
                    "H5": h5,
                    "State": state,
                    "SupATR": 1.2,
                    "ResATR": 0.8,
                }
            ],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _alert_rows(db: Path):
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT alert_key, alert_type, delivery_status, error_text FROM alerts ORDER BY id"
    ).fetchall()
    conn.close()
    return rows


def _run_status(db: Path, run_id: int) -> str:
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return row[0]


def test_runner_first_run_writes_snapshots_without_inventory_storm(
    tmp_path: Path,
) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"
    _write_ui(ui)

    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    assert result.exit_code == 0
    assert result.status == "success"
    assert result.snapshots_written == 1
    assert result.candidates_count == 0
    assert count_rows(db, "runs") == 1
    assert count_rows(db, "symbol_snapshots") == 1
    assert count_rows(db, "alerts") == 0


def test_runner_detects_and_records_state_alert_on_second_run(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    _write_ui(ui, state="clean")
    run_once_alert_service(
        AlertRunnerConfig(
            db_path=db, ui_path=ui, telegram_mode="dry-run", no_refresh=True
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    _write_ui(ui, state="DMG")
    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db, ui_path=ui, telegram_mode="dry-run", no_refresh=True
        ),
        now_utc="2026-05-01T15:15:00Z",
    )

    assert result.exit_code == 0
    assert result.candidates_count == 1
    assert result.allowed_count == 1
    rows = _alert_rows(db)
    assert len(rows) == 1
    assert rows[0][1] == "held_band_state_degraded"
    assert rows[0][2] == "dry-run"


def test_runner_records_forecast_divergence_alert_and_suppresses_duplicate(
    tmp_path: Path,
) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    _write_ui(ui, state="clean", h1=60, h5=68)
    result1 = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db, ui_path=ui, telegram_mode="dry-run", no_refresh=True
        ),
        now_utc="2026-05-01T15:00:00Z",
    )
    result2 = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db, ui_path=ui, telegram_mode="dry-run", no_refresh=True
        ),
        now_utc="2026-05-01T15:10:00Z",
    )

    assert result1.allowed_count == 1
    assert result2.suppressed_count == 1
    rows = _alert_rows(db)
    assert len(rows) == 1
    assert rows[0][1] == "held_forecast_divergence"


def test_runner_refresh_failure_returns_exit_code_2(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "missing.json"

    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db, ui_path=ui, telegram_mode="disabled", no_refresh=False
        ),
        refresh_fn=lambda: 7,
        now_utc="2026-05-01T15:00:00Z",
    )

    assert result.exit_code == 2
    assert result.status == "failed"
    assert _run_status(db, result.run_id) == "failed"
    assert count_rows(db, "system_events") == 1


def test_runner_uses_injected_telegram_sender_in_test_mode(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"
    cfg = tmp_path / "telegram.json"
    cfg.write_text(
        json.dumps({"mode": "test", "bot_token": "token", "chat_id": "chat"}),
        encoding="utf-8",
    )

    _write_ui(ui, state="clean")
    run_once_alert_service(
        AlertRunnerConfig(
            db_path=db, ui_path=ui, telegram_config_path=cfg, no_refresh=True
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    _write_ui(ui, state="DMG")
    sender = Mock()
    response = Mock()
    sender.return_value = response
    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db, ui_path=ui, telegram_config_path=cfg, no_refresh=True
        ),
        telegram_sender=sender,
        now_utc="2026-05-01T15:15:00Z",
    )

    assert result.allowed_count == 1
    sender.assert_called_once()
    data = sender.call_args.args[1]
    assert data["text"].startswith("TEST: SPY held state/score degraded")


def test_runner_main_supports_no_refresh_fixture_mode(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"
    _write_ui(ui)

    code = main(
        [
            "--db",
            str(db),
            "--ui",
            str(ui),
            "--telegram-mode",
            "dry-run",
            "--no-refresh",
        ]
    )

    assert code == 0
    assert count_rows(db, "runs") == 1
    assert count_rows(db, "symbol_snapshots") == 1


def test_runner_records_blend_divergence_alert(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    _write_ui(ui, state="clean", h1=71, h5=70, blend=66)
    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    assert result.allowed_count == 1
    rows = _alert_rows(db)
    assert len(rows) == 1
    assert rows[0][0] == "held_forecast_divergence:SPY:blend"
    assert rows[0][1] == "held_forecast_divergence"


def test_runner_records_unhealthy_floor_alert(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    _write_ui(ui, state="clean", c=56, h1=54, h5=56, blend=56)
    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
            healthy_score_floor=55,
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    assert result.allowed_count == 1
    rows = _alert_rows(db)
    assert len(rows) == 1
    assert rows[0][0] == "held_unhealthy_floor:SPY:h1"
    assert rows[0][1] == "held_unhealthy_floor"


def test_runner_records_score_band_degradation_alert(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    _write_ui(ui, state="clean", c=72, h1=69, h5=68, blend=70)
    run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    _write_ui(ui, state="clean", c=68, h1=69, h5=68, blend=70)
    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
        ),
        now_utc="2026-05-01T15:15:00Z",
    )

    assert result.allowed_count == 1
    rows = _alert_rows(db)
    assert len(rows) == 1
    assert rows[0][0] == "held_band_state_degradation:SPY:c"
    assert rows[0][1] == "held_band_state_degraded"


def test_runner_does_not_alert_on_score_band_improvement(tmp_path: Path) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    _write_ui(ui, state="DMG", c=54, h1=56, h5=56, blend=56)
    run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
            healthy_score_floor=40,
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    _write_ui(ui, state="clean", c=68, h1=68, h5=68, blend=68)
    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
            healthy_score_floor=40,
        ),
        now_utc="2026-05-01T15:15:00Z",
    )

    assert result.allowed_count == 0
    rows = _alert_rows(db)
    assert rows == []


def test_runner_records_significant_score_drop_alert_without_band_change(
    tmp_path: Path,
) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    _write_ui(ui, state="clean", c=84, h1=84, h5=84, blend=84)
    run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
            score_drop_threshold=7,
        ),
        now_utc="2026-05-01T15:00:00Z",
    )

    _write_ui(ui, state="clean", c=76, h1=84, h5=84, blend=84)
    result = run_once_alert_service(
        AlertRunnerConfig(
            db_path=db,
            ui_path=ui,
            telegram_mode="dry-run",
            no_refresh=True,
            score_drop_threshold=7,
        ),
        now_utc="2026-05-01T15:15:00Z",
    )

    assert result.allowed_count == 1
    rows = _alert_rows(db)
    assert len(rows) == 1
    assert rows[0][0] == "held_significant_score_drop:SPY:c"
    assert rows[0][1] == "held_significant_score_drop"
