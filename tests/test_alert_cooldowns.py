from pathlib import Path

from market_health.alert_cooldowns import (
    AlertCooldownConfig,
    AlertHistoryEvent,
    apply_alert_cooldowns,
    read_alert_history_from_store,
)
from market_health.alert_detectors import AlertCandidate
from market_health.alert_store import add_alert, start_run


def _candidate(
    *,
    key: str = "position_state:SPY:clean->DMG",
    severity: str = "warning",
    alert_type: str = "position_state_changed",
) -> AlertCandidate:
    return AlertCandidate(
        alert_key=key,
        alert_type=alert_type,
        severity=severity,
        symbol="SPY",
        title="SPY state changed",
        message="SPY state changed.",
        payload={"symbol": "SPY"},
    )


def test_alert_cooldown_suppresses_repeated_identical_alert() -> None:
    candidate = _candidate()
    history = [
        AlertHistoryEvent(
            alert_key=candidate.alert_key,
            severity="warning",
            ts_utc="2026-05-01T15:00:00Z",
            alert_type=candidate.alert_type,
        )
    ]

    allowed, suppressed = apply_alert_cooldowns(
        candidates=[candidate],
        history=history,
        now_utc="2026-05-01T15:10:00Z",
    )

    assert allowed == []
    assert len(suppressed) == 1
    assert suppressed[0].candidate == candidate
    assert suppressed[0].matched_event == history[0]
    assert suppressed[0].reason == "cooldown:10m<60m"


def test_alert_cooldown_allows_after_default_window() -> None:
    candidate = _candidate()
    history = [
        AlertHistoryEvent(
            alert_key=candidate.alert_key,
            severity="warning",
            ts_utc="2026-05-01T14:00:00Z",
            alert_type=candidate.alert_type,
        )
    ]

    allowed, suppressed = apply_alert_cooldowns(
        candidates=[candidate],
        history=history,
        now_utc="2026-05-01T15:01:00Z",
    )

    assert allowed == [candidate]
    assert suppressed == []


def test_alert_cooldown_allows_when_severity_changes() -> None:
    candidate = _candidate(severity="critical")
    history = [
        AlertHistoryEvent(
            alert_key=candidate.alert_key,
            severity="warning",
            ts_utc="2026-05-01T15:00:00Z",
            alert_type=candidate.alert_type,
        )
    ]

    allowed, suppressed = apply_alert_cooldowns(
        candidates=[candidate],
        history=history,
        now_utc="2026-05-01T15:05:00Z",
    )

    assert allowed == [candidate]
    assert suppressed == []


def test_alert_cooldown_uses_shorter_critical_window() -> None:
    candidate = _candidate(severity="critical")
    history = [
        AlertHistoryEvent(
            alert_key=candidate.alert_key,
            severity="critical",
            ts_utc="2026-05-01T15:00:00Z",
            alert_type=candidate.alert_type,
        )
    ]

    allowed, suppressed = apply_alert_cooldowns(
        candidates=[candidate],
        history=history,
        now_utc="2026-05-01T15:16:00Z",
        config=AlertCooldownConfig(
            default_cooldown_minutes=60,
            critical_cooldown_minutes=15,
        ),
    )

    assert allowed == [candidate]
    assert suppressed == []


def test_alert_cooldown_suppresses_critical_inside_short_window() -> None:
    candidate = _candidate(severity="critical")
    history = [
        AlertHistoryEvent(
            alert_key=candidate.alert_key,
            severity="critical",
            ts_utc="2026-05-01T15:00:00Z",
            alert_type=candidate.alert_type,
        )
    ]

    allowed, suppressed = apply_alert_cooldowns(
        candidates=[candidate],
        history=history,
        now_utc="2026-05-01T15:05:00Z",
        config=AlertCooldownConfig(
            default_cooldown_minutes=60,
            critical_cooldown_minutes=15,
        ),
    )

    assert allowed == []
    assert len(suppressed) == 1
    assert suppressed[0].reason == "cooldown:5m<15m"


def test_alert_cooldown_uses_shorter_system_health_window() -> None:
    candidate = _candidate(
        key="system_health:refresh_failed",
        severity="warning",
        alert_type="system_health",
    )
    history = [
        AlertHistoryEvent(
            alert_key=candidate.alert_key,
            severity="warning",
            ts_utc="2026-05-01T15:00:00Z",
            alert_type=candidate.alert_type,
        )
    ]

    allowed, suppressed = apply_alert_cooldowns(
        candidates=[candidate],
        history=history,
        now_utc="2026-05-01T15:20:00Z",
        config=AlertCooldownConfig(
            default_cooldown_minutes=60,
            system_health_cooldown_minutes=15,
        ),
    )

    assert allowed == [candidate]
    assert suppressed == []


def test_alert_history_can_be_read_from_sqlite_store(tmp_path: Path) -> None:
    db = tmp_path / "market_health_alerts.v1.sqlite"
    run_id = start_run(db_path=db, mode="dry-run", trigger_name="manual")

    add_alert(
        db_path=db,
        run_id=run_id,
        alert_key="position_state:SPY:clean->DMG",
        alert_type="position_state_changed",
        severity="warning",
        symbol="SPY",
        title="SPY state changed",
        message="SPY changed to DMG.",
        ts_utc="2026-05-01T15:00:00Z",
    )

    history = read_alert_history_from_store(db_path=db)

    assert history == [
        AlertHistoryEvent(
            alert_key="position_state:SPY:clean->DMG",
            severity="warning",
            ts_utc="2026-05-01T15:00:00Z",
            alert_type="position_state_changed",
        )
    ]


def test_alert_cooldown_multiple_candidates_mixed_allowed_and_suppressed() -> None:
    repeated = _candidate(key="position_state:SPY:clean->DMG")
    new = _candidate(key="position_state:XLF:clean->BRK")
    history = [
        AlertHistoryEvent(
            alert_key=repeated.alert_key,
            severity="warning",
            ts_utc="2026-05-01T15:00:00Z",
            alert_type=repeated.alert_type,
        )
    ]

    allowed, suppressed = apply_alert_cooldowns(
        candidates=[repeated, new],
        history=history,
        now_utc="2026-05-01T15:10:00Z",
    )

    assert allowed == [new]
    assert [d.candidate for d in suppressed] == [repeated]
