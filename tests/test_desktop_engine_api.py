import json
import numpy as np
import pandas as pd
import pytest
from market_health import engine
from market_health.engine_api import (
    live_scan,
    snapshot_scan,
    rows_from_engine,
    scoring_universe,
)
from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe
from market_health.recommendations_engine import blended_utility_from_scores


def frame(symbol):
    close = np.linspace(100, 130, 100) + (0.5 if symbol == "XLE" else 0)
    return pd.DataFrame(
        dict(
            Open=close,
            High=close + 1,
            Low=close - 1,
            Close=close,
            Volume=np.full(100, 1e6),
        ),
        index=pd.date_range("2026-06-01", periods=100, freq="B"),
    )


def test_adapter_matches_existing_numerical_engines(monkeypatch):
    monkeypatch.setattr(
        engine.time if hasattr(engine, "time") else __import__("time"),
        "sleep",
        lambda _: None,
    )
    engine._DOWNLOAD_CACHE.clear()
    direct = engine.compute_scores(
        sectors=["XLE"], ttl_sec=0, download_fn=lambda s, **kw: frame(s)
    )
    bars = frame("XLE")
    ohlcv = OHLCV(
        close=bars.Close.tolist(),
        high=bars.High.tolist(),
        low=bars.Low.tolist(),
        volume=bars.Volume.tolist(),
    )
    forecast = compute_forecast_universe(
        universe={"XLE": ohlcv},
        spy=OHLCV(close=frame("SPY").Close.tolist()),
        vix_close=frame("^VIX").Close.tolist(),
        horizons_trading_days=(1, 5),
    )
    expected = blended_utility_from_scores(direct, forecast_scores=forecast)["XLE"]
    scan = live_scan(["XLE"], download_fn=lambda s, **kw: frame(s))
    row = scan.rows[0]
    assert row.c == pytest.approx(expected["current_utility"] * 100)
    assert row.h1 == pytest.approx(expected["h1_utility"] * 100)
    assert row.h5 == pytest.approx(expected["h5_utility"] * 100)
    assert row.blend == pytest.approx(expected["utility"] * 100)
    assert "A=" in row.glyph and "E=" in row.glyph
    assert row.price == 130.5
    assert not row.error


def test_missing_bars_cannot_use_stale_cache(monkeypatch):
    monkeypatch.setattr(__import__("time"), "sleep", lambda _: None)
    engine._DOWNLOAD_CACHE[("BAD", "1y", "1d")] = (1e20, frame("BAD"))
    scan = live_scan(
        ["BAD", "XLE"],
        download_fn=lambda s, **kw: pd.DataFrame() if s == "BAD" else frame(s),
    )
    row = next(r for r in scan.rows if r.symbol == "BAD")
    assert row.c is None and row.error
    assert engine._DOWNLOAD_CACHE[("BAD", "1y", "1d")][0] == 1e20


def test_partial_forecast_never_renormalizes_to_a_decision():
    payload = {
        "symbol": "X",
        "categories": {c: {"checks": [{"score": 2}] * 6} for c in "ABCDE"},
    }
    row = rows_from_engine([payload], {}, asof="fixed")[0]
    assert row.blend is None and row.error


def test_snapshot_never_imports_ownership(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps(
            {
                "asof": "2026-10-25T12:00:00Z",
                "rows": [
                    {
                        "symbol": "IVE",
                        "c": 57,
                        "h1": 73,
                        "h5": 60,
                        "blend": 62,
                        "owned": True,
                    }
                ],
            }
        )
    )
    a = snapshot_scan(path)
    assert a.key == snapshot_scan(path).key
    assert not hasattr(a.rows[0], "owned")


def test_universe_preserves_inverse_and_configured_etfs(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")
    symbols = scoring_universe(["CUSTOM"])
    assert {"TECS", "FAZ", "IBIT", "IVE", "CUSTOM"} <= set(symbols)
