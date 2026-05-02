from __future__ import annotations

from typing import Any

from market_health.recommendations_engine import blended_utility_from_scores


def _score_row(symbol: str, scores: list[int]) -> dict[str, Any]:
    categories = {}
    for code, score in zip(("A", "B", "C", "D", "E"), scores):
        categories[code] = {"checks": [{"score": score}]}
    return {"symbol": symbol, "categories": categories}


def test_blend_diagnostic_explains_default_c_h1_h5_contributions() -> None:
    rows = [_score_row("SPY", [2, 1, 1, 1, 1])]  # C/current utility = 6/10 = 0.60
    forecast_scores = {
        "SPY": {
            1: {"forecast_score": 0.70},  # anchored H1 = 0.80
            5: {"forecast_score": 0.40},  # anchored H5 = 0.50
        }
    }

    out = blended_utility_from_scores(
        rows,
        forecast_scores=forecast_scores,
        forecast_horizons=(1, 5),
    )

    meta = out["SPY"]
    diag = meta["utility_blend_diagnostic"]
    components = diag["components"]

    assert round(meta["current_utility"], 6) == 0.6
    assert round(meta["h1_utility"], 6) == 0.8
    assert round(meta["h5_utility"], 6) == 0.5
    assert round(meta["utility"], 6) == 0.625

    assert diag["present_components"] == ["c", "h1", "h5"]
    assert diag["raw_weights"] == {"c": 0.5, "h1": 0.25, "h5": 0.25}
    assert round(components["c"]["contribution"], 6) == 0.3
    assert round(components["h1"]["contribution"], 6) == 0.2
    assert round(components["h5"]["contribution"], 6) == 0.125


def test_blend_diagnostic_shows_missing_horizon_weight_renormalization() -> None:
    rows = [_score_row("SPY", [2, 1, 1, 1, 1])]  # C/current utility = 0.60
    forecast_scores = {
        "SPY": {
            1: {"forecast_score": 0.70},  # anchored H1 = 0.80
        }
    }

    out = blended_utility_from_scores(
        rows,
        forecast_scores=forecast_scores,
        forecast_horizons=(1, 5),
    )

    diag = out["SPY"]["utility_blend_diagnostic"]
    components = diag["components"]

    assert diag["present_components"] == ["c", "h1"]
    assert round(diag["denominator"], 6) == 0.75
    assert components["h5"]["present"] is False
    assert components["h5"]["effective_weight"] == 0.0
    assert round(components["c"]["effective_weight"], 6) == 0.666667
    assert round(components["h1"]["effective_weight"], 6) == 0.333333
    assert round(out["SPY"]["utility"], 6) == 0.666667


def test_custom_utility_weights_are_normalized_and_explained() -> None:
    rows = [_score_row("SPY", [2, 1, 1, 1, 1])]
    forecast_scores = {
        "SPY": {
            1: {"forecast_score": 0.70},
            5: {"forecast_score": 0.40},
        }
    }

    out = blended_utility_from_scores(
        rows,
        forecast_scores=forecast_scores,
        utility_weights={"c": 2, "h1": 1, "h5": 1},
        forecast_horizons=(1, 5),
    )

    diag = out["SPY"]["utility_blend_diagnostic"]
    assert diag["raw_weights"] == {"c": 0.5, "h1": 0.25, "h5": 0.25}
    assert round(diag["blended_utility"], 6) == 0.625
