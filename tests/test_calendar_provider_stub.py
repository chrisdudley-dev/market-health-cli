from pathlib import Path
from market_health.providers.calendar_provider import (
    NullCalendarProvider,
    StubCalendarProvider,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "docs" / "examples" / "calendar_stub.sample.json"


def test_null_calendar_provider_degrades_gracefully():
    p = NullCalendarProvider()
    b = p.get_calendar(["SPY"])
    assert b.status == "no_provider"
    assert b.events == []


def test_stub_calendar_provider_normalizes_fixture():
    p = StubCalendarProvider(str(SAMPLE))
    b = p.get_calendar(["SPY", "AAPL"])
    assert b.status == "ok"
    assert len(b.events) >= 1
    assert all(ev.symbol in {"SPY", "AAPL"} for ev in b.events)
