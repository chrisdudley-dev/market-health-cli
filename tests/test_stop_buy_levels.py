from __future__ import annotations

import pandas as pd

from market_health.stop_buy_levels import generate_stop_buy_candidates


def _synthetic_frame() -> pd.DataFrame:
    close = [100.0 + i * 0.2 for i in range(80)]
    high = [value + 1.0 for value in close]
    low = [value - 1.0 for value in close]
    volume = [1000.0 + i * 10.0 for i in range(80)]

    high[-7] = close[-7] + 4.0
    low[-5] = close[-5] - 4.0

    return pd.DataFrame(
        {
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        }
    )


def test_generate_stop_buy_candidates_returns_required_fields():
    candidates = generate_stop_buy_candidates(_synthetic_frame())

    assert candidates

    for candidate in candidates:
        assert set(candidate) >= {"level", "kind", "source", "weight"}
        assert candidate["kind"] in {"floor", "ceiling"}
        assert isinstance(candidate["level"], float)
        assert isinstance(candidate["weight"], float)


def test_generate_stop_buy_candidates_includes_floor_and_ceiling_sources():
    candidates = generate_stop_buy_candidates(_synthetic_frame())

    floors = {c["source"] for c in candidates if c["kind"] == "floor"}
    ceilings = {c["source"] for c in candidates if c["kind"] == "ceiling"}

    assert "rolling_low_20d" in floors
    assert "ema_8" in floors
    assert "sma_50" in floors
    assert "rolling_vwap_20d" in floors
    assert "volume_shelf_60d" in floors

    assert "rolling_high_20d" in ceilings
    assert "swing_high" in ceilings


def test_generate_stop_buy_candidates_missing_ohlcv_fields_does_not_crash():
    df = pd.DataFrame({"Close": [10.0, 10.5, 11.0, 11.5]})

    candidates = generate_stop_buy_candidates(df)

    assert isinstance(candidates, list)
    assert all(set(c) >= {"level", "kind", "source", "weight"} for c in candidates)


def test_generate_stop_buy_candidates_empty_or_missing_close_returns_empty():
    assert generate_stop_buy_candidates(pd.DataFrame()) == []
    assert generate_stop_buy_candidates(pd.DataFrame({"High": [1, 2, 3]})) == []
