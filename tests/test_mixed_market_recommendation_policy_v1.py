from market_health.forecast_recommendations import recommend_forecast_mode


CTX = {
    "US_TECH": {
        "market": "US",
        "region": "NA",
        "family_id": "technology",
        "bucket_id": "us_tech",
    },
    "JP_TECH": {
        "market": "JP",
        "region": "APAC",
        "family_id": "technology",
        "bucket_id": "jp_tech",
    },
    "JP_FIN": {
        "market": "JP",
        "region": "APAC",
        "family_id": "financials",
        "bucket_id": "jp_fin",
    },
}


def test_mixed_us_jp_same_family_is_not_overblocked() -> None:
    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "US_TECH", "market_value": 1000.0}]},
        constraints={
            "forecast_scores": {
                "US_TECH": {1: {"forecast_score": 0.20}, 5: {"forecast_score": 0.20}},
                "JP_TECH": {1: {"forecast_score": 0.40}, 5: {"forecast_score": 0.40}},
                "JP_FIN": {1: {"forecast_score": 0.10}, 5: {"forecast_score": 0.10}},
            },
            "forecast_horizons": [1, 5],
            "horizon_trading_days": 5,
            "min_improvement_threshold": 0.05,
            "disagreement_veto_edge": 0.0,
            "max_overlap_score": 0.75,
            "exposure_contexts": CTX,
            "max_swaps_per_day": 1,
            "swaps_today": 0,
            "max_weight_per_symbol": 1.0,
            "min_distinct_symbols": 1,
            "hhi_cap": 1.0,
            "cooldown_trading_days": 0,
            "cooldown_history": [],
        },
    )

    assert rec.action == "SWAP"
    assert rec.to_symbol == "JP_TECH"
    assert rec.diagnostics["overlap"]["class"] == "same_family_different_region"


def test_mixed_us_jp_result_is_deterministic_under_tie() -> None:
    rec1 = recommend_forecast_mode(
        positions={"positions": [{"symbol": "US_TECH", "market_value": 1000.0}]},
        constraints={
            "forecast_scores": {
                "US_TECH": {1: {"forecast_score": 0.20}, 5: {"forecast_score": 0.20}},
                "JP_FIN": {1: {"forecast_score": 0.40}, 5: {"forecast_score": 0.40}},
                "JP_TECH": {1: {"forecast_score": 0.40}, 5: {"forecast_score": 0.40}},
            },
            "forecast_horizons": [1, 5],
            "horizon_trading_days": 5,
            "min_improvement_threshold": 0.05,
            "disagreement_veto_edge": 0.0,
            "max_overlap_score": 0.75,
            "exposure_contexts": CTX,
            "max_swaps_per_day": 1,
            "swaps_today": 0,
            "max_weight_per_symbol": 1.0,
            "min_distinct_symbols": 1,
            "hhi_cap": 1.0,
            "cooldown_trading_days": 0,
            "cooldown_history": [],
        },
    )

    rec2 = recommend_forecast_mode(
        positions={"positions": [{"symbol": "US_TECH", "market_value": 1000.0}]},
        constraints={
            "forecast_scores": {
                "US_TECH": {1: {"forecast_score": 0.20}, 5: {"forecast_score": 0.20}},
                "JP_FIN": {1: {"forecast_score": 0.40}, 5: {"forecast_score": 0.40}},
                "JP_TECH": {1: {"forecast_score": 0.40}, 5: {"forecast_score": 0.40}},
            },
            "forecast_horizons": [1, 5],
            "horizon_trading_days": 5,
            "min_improvement_threshold": 0.05,
            "disagreement_veto_edge": 0.0,
            "max_overlap_score": 0.75,
            "exposure_contexts": CTX,
            "max_swaps_per_day": 1,
            "swaps_today": 0,
            "max_weight_per_symbol": 1.0,
            "min_distinct_symbols": 1,
            "hhi_cap": 1.0,
            "cooldown_trading_days": 0,
            "cooldown_history": [],
        },
    )

    assert rec1.action == rec2.action
    assert rec1.to_symbol == rec2.to_symbol
    assert rec1.reason == rec2.reason
