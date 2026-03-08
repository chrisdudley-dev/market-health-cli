import pandas as pd

from market_health.engine import compute_scores


def fake_download(ticker, *args, **kwargs):
    idx = pd.bdate_range(start=pd.Timestamp("2025-01-02", tz="UTC"), periods=80)
    base = {
        "SPY": 500.0,
        "^VIX": 20.0,
        "XLE": 90.0,
        "GLDM": 50.0,
        "SGOV": 100.0,
    }.get(str(ticker), 100.0)

    vals = [base + i * 0.1 for i in range(len(idx))]
    return pd.DataFrame(
        {
            "Open": vals,
            "High": [v + 0.5 for v in vals],
            "Low": [v - 0.5 for v in vals],
            "Close": vals,
            "Volume": [1_000_000] * len(idx),
        },
        index=idx,
    )


def test_compute_scores_attaches_sector_metadata():
    rows = compute_scores(sectors=["XLE"], period="6mo", interval="1d", ttl_sec=0, download_fn=fake_download)
    row = rows[0]
    assert row["symbol"] == "XLE"
    assert row["asset_type"] == "sector"
    assert row["group"] == "SECTOR"
    assert row["metal_type"] is None
    assert row["is_basket"] is False
    assert "categories" in row


def test_compute_scores_attaches_precious_metadata():
    rows = compute_scores(sectors=["GLDM"], period="6mo", interval="1d", ttl_sec=0, download_fn=fake_download)
    row = rows[0]
    assert row["symbol"] == "GLDM"
    assert row["asset_type"] == "precious"
    assert row["group"] == "PRECIOUS"
    assert row["metal_type"] == "gold"
    assert row["is_basket"] is False
    assert "categories" in row


def test_compute_scores_attaches_parking_metadata():
    rows = compute_scores(sectors=["SGOV"], period="6mo", interval="1d", ttl_sec=0, download_fn=fake_download)
    row = rows[0]
    assert row["symbol"] == "SGOV"
    assert row["asset_type"] == "parking"
    assert row["group"] == "PARKING"
    assert row["metal_type"] is None
    assert row["is_basket"] is False
    assert "categories" in row
