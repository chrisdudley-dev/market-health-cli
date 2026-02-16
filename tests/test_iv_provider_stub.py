from pathlib import Path
from market_health.providers.iv_provider import NullIVProvider, StubIVProvider

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "docs" / "examples" / "iv_stub.sample.json"


def test_null_iv_provider_degrades_gracefully():
    p = NullIVProvider()
    b = p.get_iv(["SPY"])
    assert b.status == "no_provider"
    assert b.points == []


def test_stub_iv_provider_normalizes_fixture():
    p = StubIVProvider(str(SAMPLE))
    b = p.get_iv(["SPY", "AAPL"])
    assert b.status == "ok"
    syms = {pt.symbol for pt in b.points}
    assert "SPY" in syms and "AAPL" in syms
    for pt in b.points:
        assert 0.0 <= pt.iv
