"""UI observation metadata must preserve the existing financial/storage state."""

from market_health.android_bridge import ui_metadata
from market_health.engine_api import Scan
from market_health.policy.models import Scores
from market_health.storage.sqlite import Store


def test_empty_ui_metadata_has_no_invented_refresh(tmp_path):
    store = Store(tmp_path / "empty.sqlite3")
    before = store.path.read_bytes()
    assert ui_metadata(store) == {
        "schema_version": 1,
        "last_successful_refresh": None,
        "recent_transitions": [],
    }
    assert store.path.read_bytes() == before


def test_last_success_is_recorded_status_not_the_latest_attempt(tmp_path):
    store = Store(tmp_path / "history.sqlite3")
    store.apply_scan(
        Scan(
            "complete",
            "2026-10-26T10:00:00Z",
            (Scores("XLE", 58, 62, 60, 60),),
            "fixture",
        )
    )
    store.apply_scan(
        Scan(
            "partial",
            "2026-10-26T10:30:00Z",
            (Scores("XLE", error="missing"),),
            "fixture",
        )
    )
    store.record_failure("transport unavailable")
    before = store.path.read_bytes()
    observation = ui_metadata(store)
    assert observation["last_successful_refresh"]["scan_key"] == "complete"
    assert observation["last_successful_refresh"]["timestamp"] == "2026-10-26T10:00:00Z"
    assert store.status()["status"] == "error"
    assert store.latest()[0]["scores"]["error"] == "missing"
    assert store.path.read_bytes() == before


def test_transition_metadata_is_exact_persisted_history_and_read_only(tmp_path):
    store = Store(tmp_path / "transitions.sqlite3")
    store.save_holding("XLE", "Synthetic UI fixture", 1)
    # The same HOLD/SELL example exercised by the existing Android functional test.
    store.apply_scan(
        Scan(
            "hold", "2026-10-26T10:00:00Z", (Scores("XLE", 58, 62, 60, 60),), "fixture"
        )
    )
    store.apply_scan(
        Scan(
            "sell", "2026-10-26T10:30:00Z", (Scores("XLE", 58, 62, 53, 60),), "fixture"
        )
    )
    history = store.history()
    notifications = store.pending_notifications()
    before = store.path.read_bytes()
    assert ui_metadata(store)["recent_transitions"] == [history[0]]
    assert store.history() == history
    assert store.pending_notifications() == notifications
    assert store.path.read_bytes() == before
