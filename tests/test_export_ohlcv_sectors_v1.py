import pandas as pd

from scripts.export_ohlcv_sectors_v1 import build_ohlcv_doc


def test_build_ohlcv_doc_includes_spy_and_ewj() -> None:
    data = {
        "EWJ": pd.DataFrame(
            {
                "Close": [10.0, 10.5, 11.0],
                "High": [10.2, 10.7, 11.2],
                "Low": [9.8, 10.2, 10.8],
                "Volume": [1000, 1100, 1200],
            }
        ),
        "SPY": pd.DataFrame(
            {
                "Close": [500.0, 501.0, 502.0],
                "High": [501.0, 502.0, 503.0],
                "Low": [499.0, 500.0, 501.0],
                "Volume": [10000, 10100, 10200],
            }
        ),
    }

    doc = build_ohlcv_doc(["EWJ"], data=data)

    assert doc["schema"] == "ohlcv.sectors.v1"
    assert doc["symbols"] == ["EWJ", "SPY"]

    rows = {row["symbol"]: row for row in doc["rows"]}
    assert "EWJ" in rows
    assert "SPY" in rows
    assert rows["EWJ"]["close"] == [10.0, 10.5, 11.0]
    assert rows["SPY"]["close"] == [500.0, 501.0, 502.0]
