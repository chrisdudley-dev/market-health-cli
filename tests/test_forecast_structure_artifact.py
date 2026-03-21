from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe


def _ohlcv_trend(n: int = 90, *, direction: int = 1, step: float = 0.25) -> OHLCV:
    base = 100.0
    close = [base + direction * (i * step) for i in range(n)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    volume = [1_000_000.0 for _ in close]
    return OHLCV(close=close, high=high, low=low, volume=volume)


def test_forecast_payload_threads_structure_sidecar() -> None:
    universe = {
        "SPY": _ohlcv_trend(direction=1),
        "XLK": _ohlcv_trend(direction=1),
        "XLF": _ohlcv_trend(direction=-1),
    }

    scores = compute_forecast_universe(
        universe=universe,
        spy=universe["SPY"],
        horizons_trading_days=(1,),
    )

    payload = scores["XLK"][1]
    structure = payload["structure_summary"]
    explainability = payload["explainability"]

    assert structure["symbol"] == "XLK"
    assert "support_cushion_atr" in structure
    assert "overhead_resistance_atr" in structure
    assert "state_tags" in structure
    assert explainability["structure_sidecar_version"] == structure["version"]
    assert explainability["structure_state_tags"] == structure["state_tags"]
    assert explainability["structure_has_levels"] is True
    assert explainability["structure_no_edge"] is False


def test_forecast_payload_no_edge_is_fail_soft() -> None:
    short = OHLCV(close=[100.0, 101.0, 102.0], high=None, low=None, volume=None)
    universe = {"SPY": short, "XLK": short, "XLF": short}

    scores = compute_forecast_universe(
        universe=universe,
        spy=universe["SPY"],
        horizons_trading_days=(1,),
    )

    payload = scores["XLK"][1]
    structure = payload["structure_summary"]
    explainability = payload["explainability"]

    assert structure["nearest_support_zone"]["center"] is None
    assert structure["nearest_resistance_zone"]["center"] is None
    assert structure["state_tags"] == []
    assert explainability["structure_has_levels"] is False
    assert explainability["structure_no_edge"] is True
    assert explainability["structure_state_tags"] == []
