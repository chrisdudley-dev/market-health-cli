from market_health.forecast_recommendations import recommend_forecast_mode


def _forecast_constraints(scores, **overrides):
    base = {
        "forecast_scores": scores,
        "forecast_horizons": (1, 5),
        "horizon_trading_days": 5,
        "min_improvement_threshold": 0.01,
        "disagreement_veto_edge": 0.0,
        "max_swaps_per_day": 1,
        "swaps_today": 0,
        "cooldown_trading_days": 0,
        "cooldown_history": [],
        "max_weight_per_symbol": 1.0,
        "min_distinct_symbols": 1,
        "hhi_cap": 1.0,
    }
    base.update(overrides)
    return base


def test_pm9_diagnostics_include_all_evaluated_pairs():
    scores = {
        "AAA": {
            1: {"forecast_score": 0.20},
            5: {"forecast_score": 0.20},
        },
        "BBB": {
            1: {"forecast_score": 0.45},
            5: {"forecast_score": 0.45},
        },
        "CCC": {
            1: {"forecast_score": 0.55},
            5: {"forecast_score": 0.55},
        },
        "DDD": {
            1: {"forecast_score": 0.60},
            5: {"forecast_score": 0.60},
        },
    }

    rec = recommend_forecast_mode(
        positions={
            "positions": [
                {"symbol": "AAA", "market_value": 100.0},
                {"symbol": "BBB", "market_value": 900.0},
            ]
        },
        constraints=_forecast_constraints(scores),
    )

    assert rec.action == "SWAP"

    pairs = rec.diagnostics["candidate_pairs"]
    observed = {(p["from_symbol"], p["to_symbol"]) for p in pairs}

    assert ("AAA", "CCC") in observed
    assert ("AAA", "DDD") in observed
    assert ("BBB", "CCC") in observed
    assert ("BBB", "DDD") in observed
    assert len(pairs) == 4
