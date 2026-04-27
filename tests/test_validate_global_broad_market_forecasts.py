from __future__ import annotations

from scripts.validate_global_broad_market_forecasts import (
    _forecast_score_for_horizon,
    _return_from_tail,
    _spearman,
)


def test_forecast_score_for_horizon_reads_nested_payload():
    row = {
        "1": {"forecast_score": 0.75},
        "5": {"forecast_score": 0.62},
    }

    assert _forecast_score_for_horizon(row, 1) == 0.75
    assert _forecast_score_for_horizon(row, 5) == 0.62


def test_return_from_tail():
    assert _return_from_tail([90, 95, 100], 1) == (100 / 95) - 1.0
    assert _return_from_tail([90, 95, 100], 2) == (100 / 90) - 1.0
    assert _return_from_tail([100], 1) is None


def test_spearman_perfect_and_inverse():
    a = {"A": 3.0, "B": 2.0, "C": 1.0}
    b = {"A": 30.0, "B": 20.0, "C": 10.0}
    c = {"A": 10.0, "B": 20.0, "C": 30.0}

    assert _spearman(a, b) == 1.0
    assert _spearman(a, c) == -1.0
