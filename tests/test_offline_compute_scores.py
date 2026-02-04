import json

import numpy as np
import pandas as pd


def _make_df(symbol: str, n: int = 160) -> pd.DataFrame:
    seed = abs(hash(symbol)) % (2**32)
    rng = np.random.default_rng(seed)

    end = pd.Timestamp.now("UTC").normalize()
    idx = pd.date_range(end=end, periods=n, freq="B")

    trend = np.linspace(0, 10, n)
    noise = rng.normal(0, 0.2, n).cumsum() * 0.05

    close = 100 + trend + noise
    open_ = close + rng.normal(0, 0.15, n)
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.35, n)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.35, n)
    vol = rng.integers(1_000_000, 5_000_000, n)

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


def test_compute_scores_offline_uses_injected_downloader():
    from market_health import compute_scores

    calls = []

    def fake_download(ticker, *args, **kwargs):
        calls.append(str(ticker))
        return _make_df(str(ticker))

    sectors = ["XLI", "XLB", "XLRE"]
    res = compute_scores(
        sectors=sectors,
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )

    assert calls, "Expected injected downloader to be called"
    blob = json.dumps(res, sort_keys=True)
    for s in sectors:
        assert s in blob

    for item in res:
        h = item.get("health", {})
        assert isinstance(h.get("core_pct"), int)
        assert isinstance(h.get("trend_pct"), int)
        assert isinstance(h.get("env_pct"), int)
        assert h.get("band") in {"GREEN", "YELLOW", "RED"}
    