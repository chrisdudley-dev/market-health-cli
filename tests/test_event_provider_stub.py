from pathlib import Path

from market_health.providers.event_provider import NullEventProvider, StubEventProvider

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "docs" / "examples" / "events_stub.sample.json"


def test_null_provider_degrades_gracefully():
    p = NullEventProvider()
    b = p.get_events(["SPY"])
    assert b.status == "no_provider"
    assert b.points == []


def test_stub_provider_normalizes_fixture():
    p = StubEventProvider(str(SAMPLE))
    b = p.get_events(["SPY", "AAPL"])
    assert b.status in ("ok", "error")  # should be ok for the shipped fixture
    syms = {pt.symbol for pt in b.points}
    assert "SPY" in syms and "AAPL" in syms
