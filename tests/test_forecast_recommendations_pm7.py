from market_health.forecast_recommendations import recommend_forecast_mode


def _forecast_constraints(scores, **overrides):
    base = {
        "forecast_scores": scores,
        "forecast_horizons": (1, 5),
        "horizon_trading_days": 5,
        "min_improvement_threshold": 0.05,
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


def test_forecast_mode_prefers_higher_robust_edge():
    scores = {
        "AAA": {
            1: {"forecast_score": 0.40},
            5: {"forecast_score": 0.50},
        },
        "BBB": {
            1: {"forecast_score": 0.50},
            5: {"forecast_score": 0.56},
        },
        "CCC": {
            1: {"forecast_score": 0.80},
            5: {"forecast_score": 0.55},
        },
    }

    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "AAA", "market_value": 1000.0}]},
        constraints=_forecast_constraints(scores),
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "AAA"
    assert rec.to_symbol == "BBB"
    assert rec.diagnostics["decision_metric"] == "robust_edge"
    assert abs(rec.diagnostics["robust_edge"] - 0.06) < 1e-9


def test_forecast_mode_blocks_on_disagreement_veto():
    scores = {
        "AAA": {
            1: {"forecast_score": 0.50},
            5: {"forecast_score": 0.50},
        },
        "BBB": {
            1: {"forecast_score": 0.70},
            5: {"forecast_score": 0.49},
        },
    }

    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "AAA", "market_value": 1000.0}]},
        constraints=_forecast_constraints(scores, disagreement_veto_edge=0.0),
    )

    assert rec.action == "NOOP"
    assert "Forecast veto" in rec.reason
    assert "disagreement_veto_edge" in rec.constraints_triggered
    assert rec.diagnostics["vetoed"] is True


def test_forecast_mode_holds_when_robust_edge_is_below_threshold():
    scores = {
        "AAA": {
            1: {"forecast_score": 0.50},
            5: {"forecast_score": 0.50},
        },
        "BBB": {
            1: {"forecast_score": 0.54},
            5: {"forecast_score": 0.57},
        },
    }

    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "AAA", "market_value": 1000.0}]},
        constraints=_forecast_constraints(scores, min_improvement_threshold=0.05),
    )

    assert rec.action == "NOOP"
    assert "min_improvement_threshold" in rec.constraints_triggered
    assert abs(rec.diagnostics["robust_edge"] - 0.04) < 1e-9
