from datetime import date

from market_health.calibration_v1 import build_calibration_v1
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


def test_pm12_can_read_thresholds_from_calibration_v1_doc():
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

    calibration_doc = build_calibration_v1(
        asof_date=date(2026, 1, 1),
        thresholds={
            "min_improvement_threshold": 0.03,
            "disagreement_veto_edge": 0.0,
        },
    )

    rec = recommend_forecast_mode(
        positions={"positions": [{"symbol": "AAA", "market_value": 1000.0}]},
        constraints=_forecast_constraints(
            scores,
            min_improvement_threshold=0.05,
            calibration=calibration_doc,
        ),
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "AAA"
    assert rec.to_symbol == "BBB"
    assert rec.diagnostics["threshold"] == 0.03
