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


def test_portfolio_weighted_objective_can_prefer_replacing_non_weakest_held():
    scores = {
        "AAA": {
            1: {"forecast_score": 0.20},
            5: {"forecast_score": 0.20},
        },
        "BBB": {
            1: {"forecast_score": 0.45},
            5: {"forecast_score": 0.45},
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
    assert rec.from_symbol == "BBB"
    assert rec.to_symbol == "DDD"
