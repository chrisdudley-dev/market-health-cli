import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

from market_health.alert_detectors import AlertCandidate
from market_health.alert_runner import AlertRunnerConfig, run_once_alert_service
from market_health.alert_store import count_rows, start_run
from market_health.telegram_notifier import (
    TelegramConfig,
    send_and_record_alert_candidate,
)


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


def _alert_payloads(db: Path) -> list[dict]:
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        """
        SELECT alert_key, alert_type, delivery_status, payload_json
        FROM alerts
        ORDER BY id
        """
    ).fetchall()
    conn.close()

    out = []
    for alert_key, alert_type, delivery_status, payload_json in rows:
        out.append(
            {
                "alert_key": alert_key,
                "alert_type": alert_type,
                "delivery_status": delivery_status,
                "payload": json.loads(payload_json),
            }
        )
    return out


def test_m44_runner_stores_formatted_divergence_and_suppresses_duplicate(
    tmp_path: Path,
) -> None:
    db = tmp_path / "alerts.sqlite"
    ui = tmp_path / "market_health.ui.v1.json"

    cfg = AlertRunnerConfig(
        db_path=db,
        ui_path=ui,
        telegram_mode="dry-run",
        no_refresh=True,
        healthy_score_floor=0,
        previous_drop_threshold=100,
        score_drop_threshold=100,
    )

    _write_ui(ui, c=72, h1=69, h5=68, blend=70)
    first = run_once_alert_service(cfg, now_utc="2026-05-01T15:00:00Z")

    assert first.exit_code == 0
    assert first.candidates_count == 0
    assert count_rows(db, "symbol_snapshots") == 1
    assert count_rows(db, "alerts") == 0

    _write_ui(ui, c=72, h1=66, h5=60, blend=70)
    second = run_once_alert_service(cfg, now_utc="2026-05-01T15:15:00Z")

    assert second.exit_code == 0
    assert second.candidates_count == 2
    assert second.allowed_count == 2
    assert second.suppressed_count == 0

    rows = _alert_payloads(db)
    assert [row["alert_key"] for row in rows] == [
        "held_forecast_divergence:SPY:H1",
        "held_forecast_divergence:SPY:H5",
    ]
    assert {row["alert_type"] for row in rows} == {"held_forecast_divergence"}
    assert {row["delivery_status"] for row in rows} == {"dry-run"}

    h1_text = rows[0]["payload"]["telegram_text"]
    h5_text = rows[1]["payload"]["telegram_text"]

    assert "Rule: C>H1" in h1_text
    assert "Scores: C=72.0 | H1=66.0 | H5=60.0 | blend=70.0" in h1_text
    assert "Drop: 6.0 points; threshold=5.0" in h1_text
    assert "Rule: C>H5" in h5_text
    assert "Drop: 12.0 points; threshold=5.0" in h5_text
    assert "/root" not in h1_text
    assert "/root" not in h5_text

    third = run_once_alert_service(cfg, now_utc="2026-05-01T15:20:00Z")

    assert third.exit_code == 0
    assert third.candidates_count == 2
    assert third.allowed_count == 0
    assert third.suppressed_count == 2
    assert count_rows(db, "alerts") == 2


def test_m44_dry_run_records_rendered_text_for_all_held_alert_families(
    tmp_path: Path,
) -> None:
    db = tmp_path / "alerts.sqlite"
    run_id = start_run(
        db_path=db,
        mode="dry-run",
        trigger_name="deterministic-test",
        started_at_utc="2026-05-01T15:00:00Z",
    )
    sender = Mock()

    candidates = [
        AlertCandidate(
            alert_key="held_forecast_divergence:SPY:H1",
            alert_type="held_forecast_divergence",
            severity="warning",
            symbol="SPY",
            title="SPY forecast divergence: C > H1",
            message="SPY current score is 6.0 points above H1.",
            payload={
                "symbol": "SPY",
                "triggered_rule": "C>H1",
                "c_score": 72.0,
                "h1_score": 66.0,
                "h5_score": 60.0,
                "blend_score": 68.0,
                "drop": 6.0,
                "threshold": 5.0,
            },
        ),
        AlertCandidate(
            alert_key="held_unhealthy_floor:SPY:h1",
            alert_type="held_unhealthy_floor",
            severity="warning",
            symbol="SPY",
            title="SPY below healthy floor",
            message="SPY has held-position score fields below the healthy floor 55.0: H1=54.0.",
            payload={
                "symbol": "SPY",
                "c_score": 56.0,
                "h1_score": 54.0,
                "h5_score": 56.0,
                "blend_score": 56.0,
                "healthy_floor": 55.0,
                "breached_fields": ["H1"],
            },
        ),
        AlertCandidate(
            alert_key="held_band_state_degradation:SPY:state-c",
            alert_type="held_band_state_degraded",
            severity="warning",
            symbol="SPY",
            title="SPY held state/score degraded",
            message="SPY held position degraded.",
            payload={
                "symbol": "SPY",
                "previous_state": "HOLD",
                "current_state": "UNHEALTHY",
                "previous_values": {
                    "c_score": 72.0,
                    "h1_score": 70.0,
                    "h5_score": 69.0,
                    "blend_score": 71.0,
                },
                "current_values": {
                    "c_score": 54.0,
                    "h1_score": 50.0,
                    "h5_score": 52.0,
                    "blend_score": 53.0,
                },
                "degraded_fields": ["C", "H1", "H5", "blend"],
                "reason": "state HOLD->UNHEALTHY; C band green->red",
            },
        ),
        AlertCandidate(
            alert_key="held_significant_score_drop:SPY:c",
            alert_type="held_significant_score_drop",
            severity="warning",
            symbol="SPY",
            title="SPY significant held score drop",
            message="SPY held-position score dropped materially: C -8.0.",
            payload={
                "symbol": "SPY",
                "previous_values": {
                    "c_score": 84.0,
                    "h1_score": 84.0,
                    "h5_score": 84.0,
                    "blend_score": 84.0,
                },
                "current_values": {
                    "c_score": 76.0,
                    "h1_score": 84.0,
                    "h5_score": 84.0,
                    "blend_score": 84.0,
                },
                "drops": {"C": 8.0},
                "threshold": 7.0,
                "affected_fields": ["C"],
            },
        ),
    ]

    for candidate in candidates:
        result = send_and_record_alert_candidate(
            db_path=db,
            run_id=run_id,
            candidate=candidate,
            config=TelegramConfig(mode="dry-run"),
            sender=sender,
            ts_utc="2026-05-01T15:00:00Z",
        )
        assert result.delivery_status == "dry-run"
        assert result.sent is False

    sender.assert_not_called()

    rows = _alert_payloads(db)
    assert len(rows) == 4
    assert {row["delivery_status"] for row in rows} == {"dry-run"}

    rendered = "\n\n".join(row["payload"]["telegram_text"] for row in rows)

    assert "Rule: C>H1" in rendered
    assert "Rule: below healthy floor" in rendered
    assert "Rule: held state/score degradation" in rendered
    assert "Rule: significant score drop" in rendered
    assert "Scores: C=72.0 | H1=66.0 | H5=60.0 | blend=68.0" in rendered
    assert "Healthy floor: 55.0" in rendered
    assert "State: HOLD -> UNHEALTHY" in rendered
    assert "Drops: C -8.0" in rendered
    assert "/root" not in rendered
    assert "bot_token" not in rendered
    assert "chat_id" not in rendered
