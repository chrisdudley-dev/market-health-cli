from __future__ import annotations

import pandas as pd

from market_health.stop_buy_levels import (
    generate_stop_buy_candidates,
    strongest_stop_buy_clusters,
)


def test_clustered_executable_stop_buy_math_uses_cluster_edges_plus_atr_buffer():
    df = pd.DataFrame(
        {
            "High": [
                100.0,
                101.0,
                102.0,
                105.0,
                104.8,
                105.1,
                103.0,
                102.0,
                101.0,
                100.0,
                99.0,
                99.2,
                98.9,
                100.0,
                101.0,
                102.0,
            ],
            "Low": [
                96.0,
                97.0,
                98.0,
                100.0,
                99.8,
                100.1,
                98.0,
                97.0,
                96.0,
                95.0,
                94.0,
                94.2,
                94.1,
                95.0,
                96.0,
                97.0,
            ],
            "Close": [
                98.0,
                99.0,
                100.0,
                102.0,
                103.0,
                104.0,
                101.0,
                99.0,
                98.0,
                97.0,
                96.0,
                96.4,
                96.1,
                98.0,
                99.0,
                100.0,
            ],
            "Volume": [1000.0] * 16,
        }
    )

    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_last = float(tr.rolling(14, min_periods=5).mean().iloc[-1])

    candidates = generate_stop_buy_candidates(df)
    clusters = strongest_stop_buy_clusters(
        candidates,
        current_price=float(close.iloc[-1]),
        atr=atr_last,
        min_cluster_size=2,
    )

    assert clusters["floor"] is not None
    assert clusters["ceiling"] is not None

    stop = float(clusters["floor"]["lower"]) - (0.25 * atr_last)
    buy = float(clusters["ceiling"]["upper"]) + (0.25 * atr_last)

    assert stop < float(close.iloc[-1])
    assert buy > float(close.iloc[-1])
