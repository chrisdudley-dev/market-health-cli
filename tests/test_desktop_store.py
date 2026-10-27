import pytest
from market_health.policy import Scores
from market_health.engine_api import Scan
from market_health.storage.sqlite import Store
from market_health.application.service import size_position, RefreshService


def scan(key, s=None, source="live engine"):
    return Scan(
        key, "2026-10-25T12:00:00+00:00", (s or Scores("RPG", 58, 62, 60, 60),), source
    )


def test_restart_rescue(tmp_path):
    p = tmp_path / "db.sqlite"
    db = Store(p)
    db.save_holding("rpg", "Roth IRA", 3)
    rescue = Scores("RPG", 52, 62, 59, 56)
    assert db.apply_scan(scan("1", rescue))
    assert db.latest()[0]["action"] == "HOLD — RESCUE"
    db = Store(p)
    assert not db.apply_scan(scan("1", rescue))
    assert len(db.history()) == 1
    db.apply_scan(scan("2", rescue))
    assert db.latest()[0]["action"] == "SELL"
    assert db.latest()[0]["result"]["rescue_count"] == 2


def test_notifications_and_data_errors(tmp_path):
    db = Store(tmp_path / "db")
    db.save_holding("RPG", "Other", 3)
    db.apply_scan(scan("1"))
    assert db.pending_notifications() == []
    db.apply_scan(scan("2", Scores("RPG", 58, 62, 53, 57)))
    assert len(db.pending_notifications()) == 1
    db.apply_scan(scan("3", Scores("RPG", 58, 62, 53, 57)))
    assert len(db.pending_notifications()) == 1
    db.apply_scan(scan("4", Scores("RPG", error="network failed")))
    assert len(db.pending_notifications()) == 1
    db.apply_scan(scan("5"))
    assert len(db.pending_notifications()) == 2
    assert "SELL → HOLD" in db.pending_notifications()[-1]["body"]


def test_local_ownership_and_multiaccount(tmp_path):
    db = Store(tmp_path / "db")
    db.save_holding("RPG", "A", 1)
    db.save_holding("RPG", "B", 2)
    db.apply_scan(scan("1"))
    assert len(db.latest()) == 1
    assert sorted(db.latest()[0]["accounts"]) == ["A", "B"]
    db.remove_holding("RPG", "A")
    assert len(db.holdings()) == 1
    db.remove_holding("RPG", "B")
    db.apply_scan(scan("2"))
    assert not db.latest()[0]["owned"]
    assert db.latest()[0]["action"] == "UNKNOWN"
    assert len(db.history(account="A")) == 1


def test_error_preserves_rescue_and_absent_holding(tmp_path):
    db = Store(tmp_path / "db")
    db.save_holding("RPG", "A", 3)
    db.apply_scan(scan("1", Scores("RPG", 52, 62, 59, 56)))
    db.apply_scan(scan("2", Scores("RPG", error="missing")))
    db.save_holding("RPG", "A", 4)
    db.apply_scan(scan("3", Scores("RPG", 52, 62, 59, 56)))
    assert db.latest()[0]["action"] == "SELL"
    db.save_holding("IVE", "B", 2)
    db.apply_scan(scan("4"))
    assert (
        next(x for x in db.latest() if x["symbol"] == "IVE")["action"] == "DATA ERROR"
    )


def test_buy_transition_setting_and_no_snapshot_notifications(tmp_path):
    db = Store(tmp_path / "db")
    db.save_settings({"notify_buy": True})
    db.apply_scan(scan("1", Scores("IVE", 55, 55, 55, 55)))
    db.apply_scan(scan("2", Scores("IVE", 55, 58, 58, 60)))
    db.apply_scan(scan("3", Scores("IVE", 55, 58, 58, 60)))
    assert len(db.pending_notifications()) == 1
    db.save_holding("RPG", "A", 1)
    db.apply_scan(
        scan("4", Scores("RPG", 58, 60, 60, 59), "local snapshot (historical)")
    )
    db.apply_scan(
        scan("5", Scores("RPG", 49, 90, 90, 80), "local snapshot (historical)")
    )
    assert len(db.pending_notifications()) == 1


def test_atomic_rollback(tmp_path):
    db = Store(tmp_path / "db")
    db.apply_scan(scan("1"))
    with pytest.raises(ValueError):
        db.apply_scan(Scan("2", "now", (Scores("X"), Scores("X")), "live engine"))
    assert len(db.history()) == 1
    with db.connect() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 1
    db.save_settings({"net_liq": 6000, "cash": 1000})
    assert Store(db.path).settings()["net_liq"] == 6000
    with pytest.raises(ValueError):
        db.save_holding("BAD SYMBOL", "A", 1)
    with pytest.raises(ValueError):
        db.save_settings({"target_positions": 0})


def test_service_failure_does_not_create_decisions(tmp_path, monkeypatch):
    db = Store(tmp_path / "db")
    db.apply_scan(scan("1"))

    def fail(*a, **kw):
        raise OSError("offline")

    monkeypatch.setattr("market_health.application.service.live_scan", fail)
    with pytest.raises(OSError):
        RefreshService(db).refresh()
    assert len(db.history()) == 1
    assert db.status()["status"] == "error"


def test_sizing():
    d = size_position(6000, 8, 238)
    assert d.slot == 750 and d.shares == 3
    assert "floor(750.00 / 238) = 3" in d.explanation
    assert size_position(None, 8, 238) is None
    assert size_position(6000, 0, 238) is None
    assert size_position(6000, 8, 0) is None
