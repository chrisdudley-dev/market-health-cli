import pandas as pd

from market_health.dashboard_legacy import _backfill_missing_forecast_scores
from market_health.recommendations_engine import blended_utility_from_scores


def _row(symbol: str, pts: int, checks: int = 10, **extra):
    checks_list = [{"label": f"c{i}", "score": 0} for i in range(checks)]
    remaining = pts
    i = 0
    while remaining > 0 and i < checks:
        add = 2 if remaining >= 2 else 1
        checks_list[i]["score"] = add
        remaining -= add
        i += 1
    row = {"symbol": symbol, "categories": {"A": {"checks": checks_list}}}
    row.update(extra)
    return row


def _df(base: float, step: float = 0.25, n: int = 90):
    vals = [base + i * step for i in range(n)]
    return pd.DataFrame(
        {
            "Open": vals,
            "High": [v + 0.5 for v in vals],
            "Low": [v - 0.5 for v in vals],
            "Close": vals,
            "Volume": [1_000_000] * len(vals),
        }
    )


def test_dashboard_backfills_missing_etf_forecast_scores():
    rows = [
        _row("XLB", 8, asset_type="sector", group="SECTOR"),
        _row("IBIT", 8, asset_type="etf", group="ETF"),
    ]

    forecast_doc = {
        "horizons_trading_days": [1, 5],
        "scores": {
            "XLB": {
                "1": {"forecast_score": 0.55},
                "5": {"forecast_score": 0.60},
            }
        },
    }

    data = {
        "SPY": _df(100.0, 0.20),
        "XLB": _df(90.0, 0.10),
        "IBIT": _df(50.0, 0.40),
    }

    merged = _backfill_missing_forecast_scores(
        forecast_doc,
        symbols=["XLB", "IBIT"],
        data=data,
        horizons=(1, 5),
    )

    util = blended_utility_from_scores(
        rows,
        forecast_scores=merged["scores"],
        forecast_horizons=(1, 5),
    )

    assert "IBIT" in merged["scores"]
    assert util["IBIT"]["h1_utility"] is not None
    assert util["IBIT"]["h5_utility"] is not None
    assert util["IBIT"]["utility"] is not None
