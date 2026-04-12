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


def test_etf_candidate_can_be_selected_in_forecast_mode():
    scores = {
        "AAA": {
            1: {"forecast_score": 0.20},
            5: {"forecast_score": 0.20},
        },
        "ETHA": {
            1: {"forecast_score": 0.45},
            5: {"forecast_score": 0.45},
        },
        "IBIT": {
            1: {"forecast_score": 0.60},
            5: {"forecast_score": 0.60},
        },
    }

    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "AAA", "market_value": 1000.0}]},
        constraints=_forecast_constraints(scores),
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "AAA"
    assert rec.to_symbol == "IBIT"
    assert rec.diagnostics["best_candidate"] == "IBIT"
    assert rec.diagnostics["selected_pair"]["to_symbol"] == "IBIT"


def test_etf_candidates_appear_in_candidate_pairs_diagnostics():
    scores = {
        "AAA": {
            1: {"forecast_score": 0.20},
            5: {"forecast_score": 0.20},
        },
        "ETHA": {
            1: {"forecast_score": 0.45},
            5: {"forecast_score": 0.45},
        },
        "IBIT": {
            1: {"forecast_score": 0.60},
            5: {"forecast_score": 0.60},
        },
    }

    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "AAA", "market_value": 1000.0}]},
        constraints=_forecast_constraints(scores),
    )

    assert rec.action == "SWAP"

    pairs = rec.diagnostics["candidate_pairs"]
    observed = {(p["from_symbol"], p["to_symbol"]) for p in pairs}

    assert ("AAA", "ETHA") in observed
    assert ("AAA", "IBIT") in observed
