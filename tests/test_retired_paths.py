from pathlib import Path
import pytest
from market_health.recommendations_engine import recommend


def test_legacy_decisions_fail_closed():
    with pytest.raises(RuntimeError, match="retired"):
        recommend(positions={"positions": [{"symbol": "X"}]}, scores=[], constraints={})


def test_brokerage_implementations_removed():
    assert not list(Path("market_health/brokers").glob("*.py"))
    assert not list(Path("scripts").glob("*schwab*"))


def test_old_position_refresh_cannot_fetch_accounts():
    for name in (
        "scripts/cache/refresh_positions_cache.sh",
        "scripts/jerboa/bin/jerboa-market-health-positions-refresh",
    ):
        text = Path(name).read_text()
        assert "exit 2" in text and "manual" in text
        assert "http" not in text


def test_desktop_has_no_old_decision_imports():
    for p in Path("market_health/desktop").glob("*.py"):
        source = p.read_text()
        for forbidden in (
            "brokers",
            "forecast_recommendations",
            "weakest",
            "apply_swap",
            "render_reco",
        ):
            assert forbidden not in source
