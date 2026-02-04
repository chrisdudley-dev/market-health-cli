import json

import numpy as np
import pandas as pd


def _make_df(symbol: str, n: int = 160) -> pd.DataFrame:
    # deterministic pseudo-data so tests never hit the network
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


def test_compute_scores_offline(monkeypatch):
    import market_health.engine as eng

    def fake_download_many(tickers, *args, **kwargs):
        return {tk: _make_df(tk) for tk in tickers}

    # Patch at the best available layer (robust across refactors)
    if hasattr(eng, "download_many"):
        monkeypatch.setattr(eng, "download_many", fake_download_many)
    elif hasattr(eng, "_yf_download"):
        monkeypatch.setattr(
            eng, "_yf_download", lambda *a, **k: _make_df(str(a[0]) if a else "SPY")
        )
    elif hasattr(eng, "yf") and hasattr(eng.yf, "download"):
        monkeypatch.setattr(
            eng.yf, "download", lambda *a, **k: _make_df(str(a[0]) if a else "SPY")
        )

    from market_health import compute_scores

    sectors = ["XLI", "XLB", "XLRE"]
    res = compute_scores(sectors=sectors, period="6mo", interval="1d", ttl_sec=0)

    # Ensure JSON-serializable and contains all sector tickers somewhere in the payload
    blob = json.dumps(res, sort_keys=True)
    for s in sectors:
        assert s in blob
