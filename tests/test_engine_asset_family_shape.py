import pandas as pd

from market_health.engine import compute_scores


def fake_download(ticker, *args, **kwargs):
    idx = pd.bdate_range(start=pd.Timestamp("2025-01-02", tz="UTC"), periods=80)
    base = {
        "SPY": 500.0,
        "^VIX": 20.0,
        "XLE": 90.0,
        "TECS": 40.0,
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


def _assert_shape(row):
    assert set(row.keys()) >= {
        "symbol",
        "asset_type",
        "group",
        "metal_type",
        "is_basket",
        "categories",
    }
    cats = row["categories"]
    assert set(cats.keys()) == {"A", "B", "C", "D", "E"}
    for dim in ("A", "B", "C", "D", "E"):
        checks = cats[dim]["checks"]
        assert isinstance(checks, list)
        assert len(checks) == 6
        for chk in checks:
            assert isinstance(chk["label"], str)
            assert chk["score"] in (0, 1, 2)


def test_shape_sector():
    row = compute_scores(
        sectors=["XLE"],
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )[0]
    assert row["asset_type"] == "sector"
    _assert_shape(row)


def test_shape_inverse():
    row = compute_scores(
        sectors=["TECS"],
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )[0]
    assert row["asset_type"] == "inverse"
    _assert_shape(row)


def test_shape_precious():
    row = compute_scores(
        sectors=["GLDM"],
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )[0]
    assert row["asset_type"] == "precious"
    _assert_shape(row)


def test_shape_parking():
    row = compute_scores(
        sectors=["SGOV"],
        period="6mo",
        interval="1d",
        ttl_sec=0,
        download_fn=fake_download,
    )[0]
    assert row["asset_type"] == "parking"
    _assert_shape(row)
