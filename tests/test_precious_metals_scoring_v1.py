import pandas as pd

from market_health.engine import compute_scores


def fake_download(ticker, *args, **kwargs):
    idx = pd.bdate_range(start=pd.Timestamp("2025-01-02", tz="UTC"), periods=80)
    base = {
        "SPY": 500.0,
        "^VIX": 20.0,
        "GLDM": 50.0,
        "GLTR": 55.0,
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


def _labels(row, dim):
    return [chk["label"] for chk in row["categories"][dim]["checks"]]


def _scores(row, dim):
    return [chk["score"] for chk in row["categories"][dim]["checks"]]


def test_precious_scoring_keeps_ae_shape():
    row = compute_scores(
        sectors=["GLDM"],
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )[0]

    assert row["symbol"] == "GLDM"
    assert row["asset_type"] == "precious"
    assert row["group"] == "PRECIOUS"

    assert set(row["categories"].keys()) == {"A", "B", "C", "D", "E"}
    for dim in ("A", "B", "C", "D", "E"):
        checks = row["categories"][dim]["checks"]
        assert isinstance(checks, list)
        assert len(checks) == 6
        for chk in checks:
            assert isinstance(chk["label"], str)
            assert chk["score"] in (0, 1, 2)


def test_precious_e_neutralizes_sector_rank_and_breadth():
    row = compute_scores(
        sectors=["GLDM"],
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )[0]

    assert _labels(row, "E") == [
        "SPY Trend",
        "Sector Rank",
        "Breadth",
        "VIX Regime",
        "3-Day RS",
        "Drivers",
    ]

    scores = _scores(row, "E")
    assert scores[1] == 1
    assert scores[2] == 1
    assert all(score in (0, 1, 2) for score in scores)


def test_gltr_basket_metadata_and_e_behavior():
    row = compute_scores(
        sectors=["GLTR"],
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )[0]

    assert row["symbol"] == "GLTR"
    assert row["asset_type"] == "precious"
    assert row["group"] == "PRECIOUS"
    assert row["metal_type"] == "basket"
    assert row["is_basket"] is True

    scores = _scores(row, "E")
    assert scores[1] == 1
    assert scores[2] == 1
