from pathlib import Path

from market_health.providers.flow_provider import NullFlowProvider, StubFlowProvider

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "docs" / "examples" / "flow_stub.sample.json"

def test_null_provider_degrades_gracefully():
    p = NullFlowProvider()
    b = p.get_flow(["SPY"])
    assert b.status == "no_provider"
    assert b.points == []

def test_stub_provider_normalizes_fixture():
    p = StubFlowProvider(str(SAMPLE))
    b = p.get_flow(["SPY", "AAPL"])
    assert b.status == "ok"
    syms = {pt.symbol for pt in b.points}
    assert "SPY" in syms and "AAPL" in syms
