from market_health.forecast_recommendations import recommend_forecast_mode


CTX = {
    "JPTECH_A": {
        "market": "JP",
        "region": "APAC",
        "family_id": "technology",
        "bucket_id": "jp_tech_a",
    },
    "JPTECH_B": {
        "market": "JP",
        "region": "APAC",
        "family_id": "technology",
        "bucket_id": "jp_tech_a",
    },
    "USTECH_A": {
        "market": "US",
        "region": "NA",
        "family_id": "technology",
        "bucket_id": "us_tech_a",
    },
    "USUTIL_A": {
        "market": "US",
        "region": "NA",
        "family_id": "utilities",
        "bucket_id": "us_util_a",
    },
}


def test_forecast_overlap_policy_allows_same_family_different_region() -> None:
    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "USTECH_A", "market_value": 1000.0}]},
        constraints={
            "forecast_scores": {
                "USTECH_A": {
                    1: {"forecast_score": 0.20},
                    5: {"forecast_score": 0.20},
                },
                "JPTECH_A": {
                    1: {"forecast_score": 0.40},
                    5: {"forecast_score": 0.40},
                },
                "USUTIL_A": {
                    1: {"forecast_score": 0.10},
                    5: {"forecast_score": 0.10},
                },
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
    assert rec.from_symbol == "USTECH_A"
    assert rec.to_symbol == "JPTECH_A"
    assert rec.diagnostics["overlap"]["class"] == "same_family_different_region"
    assert rec.diagnostics["overlap_ok"] is True


def test_forecast_overlap_policy_blocks_same_bucket_same_market() -> None:
    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "JPTECH_A", "market_value": 1000.0}]},
        constraints={
            "forecast_scores": {
                "JPTECH_A": {
                    1: {"forecast_score": 0.20},
                    5: {"forecast_score": 0.20},
                },
                "JPTECH_B": {
                    1: {"forecast_score": 0.40},
                    5: {"forecast_score": 0.40},
                },
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

    assert rec.action == "NOOP"
    assert "overlap_policy_v1" in rec.constraints_triggered
    assert rec.diagnostics["overlap"]["class"] == "same_bucket_same_market"
    assert rec.diagnostics["overlap_ok"] is False
