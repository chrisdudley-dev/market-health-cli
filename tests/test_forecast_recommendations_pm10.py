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


def test_pm10_diagnostics_include_selected_pair_summary():
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

    selected = rec.diagnostics["selected_pair"]
    assert selected["from_symbol"] == rec.from_symbol
    assert selected["to_symbol"] == rec.to_symbol
    assert selected["decision_metric"] == rec.diagnostics["decision_metric"]
    assert selected["robust_edge"] == rec.diagnostics["robust_edge"]
    assert selected["weighted_robust_edge"] == rec.diagnostics["weighted_robust_edge"]
    assert selected["edges_by_h"] == rec.diagnostics["edges_by_h"]
