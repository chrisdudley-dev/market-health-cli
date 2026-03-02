from pathlib import Path

from market_health.ledger import append_event, read_events


def test_ledger_appends_event(tmp_path: Path):
    db = tmp_path / "ledger.v0.sqlite"

    append_event(
        db_path=db,
        event_type="recommendation.v1",
        payload={"schema": "recommendations.v1", "recommendation": {"action": "NOOP"}},
        ts_utc="2026-02-22T00:00:00Z",
    )

    ev = read_events(db, limit=10)
    assert len(ev) == 1
    assert ev[0]["event_type"] == "recommendation.v1"
    assert ev[0]["ts_utc"] == "2026-02-22T00:00:00Z"
    assert ev[0]["payload"]["schema"] == "recommendations.v1"
