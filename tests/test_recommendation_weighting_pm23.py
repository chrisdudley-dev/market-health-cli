from __future__ import annotations

import datetime as dt

from market_health.calibration_v1 import build_calibration_v1, validate_calibration_v1
from market_health.forecast_recommendations import recommend_forecast_mode
from market_health.recommendation_weighting import (
    infer_symbol_family,
    resolve_utility_weights,
)


def test_calibration_v1_includes_weighting_defaults_and_validates() -> None:
    doc = build_calibration_v1(asof_date=dt.date(2026, 3, 22))
    assert validate_calibration_v1(doc) == []
    assert "weighting" in doc
    assert doc["weighting"]["base_utility_weights"] == {
        "c": 0.50,
        "h1": 0.25,
        "h5": 0.25,
    }


def test_resolve_utility_weights_preserves_fallback_defaults() -> None:
    out = resolve_utility_weights(
        base_weights={"c": 0.50, "h1": 0.25, "h5": 0.25},
        weighting_profile={},
        regime_key="unknown",
        symbol_family="unknown",
    )
    assert out["regime"] == "neutral"
    assert out["symbol_family"] == "unknown"
    assert out["weights"] == {"c": 0.50, "h1": 0.25, "h5": 0.25}


def test_infer_symbol_family_is_deterministic() -> None:
    assert infer_symbol_family("XLE") == "sector_etf"
    assert infer_symbol_family("GLD") == "metals"
    assert infer_symbol_family("SPY") == "broad_index"


def test_forecast_mode_records_effective_weights_in_active_path() -> None:
    scores = {
        "XLE": {
            "1": {
                "forecast_score": 0.60,
                "structure_summary": {
                    "support_cushion_atr": 0.80,
                    "overhead_resistance_atr": 0.10,
                    "state_tags": ["breakout_ready"],
                },
            },
            "5": {
                "forecast_score": 0.70,
                "structure_summary": {
                    "support_cushion_atr": 0.80,
                    "overhead_resistance_atr": 0.10,
                    "state_tags": ["breakout_ready"],
                },
            },
        },
        "GLD": {
            "1": {
                "forecast_score": 0.40,
                "structure_summary": {
                    "support_cushion_atr": 1.20,
                    "overhead_resistance_atr": 0.20,
                    "state_tags": ["reclaim_ready"],
                },
            },
            "5": {
                "forecast_score": 0.80,
                "structure_summary": {
                    "support_cushion_atr": 1.20,
                    "overhead_resistance_atr": 0.20,
                    "state_tags": ["reclaim_ready"],
                },
            },
        },
    }

    rec = recommend_forecast_mode(
        positions=["XLE"],
        constraints={
            "forecast_scores": scores,
            "forecast_horizons": [1, 5],
            "min_improvement_threshold": 0.12,
            "disagreement_veto_edge": 0.08,
            "current_utilities": {
                "XLE": {"utility": 0.50},
                "GLD": {"utility": 0.30},
            },
            "regime_key": "risk_off",
            "symbol_family_by_symbol": {
                "XLE": "sector_etf",
                "GLD": "metals",
            },
            "weighting": {
                "base_utility_weights": {"c": 0.50, "h1": 0.25, "h5": 0.25},
                "regime_overrides": {
                    "risk_off": {"c": 0.60, "h1": 0.20, "h5": 0.20},
                },
                "symbol_family_overrides": {
                    "sector_etf": {"c": 0.45, "h1": 0.25, "h5": 0.30},
                    "metals": {"c": 0.35, "h1": 0.20, "h5": 0.45},
                },
            },
            "calibration_source": "calibration.v1",
        },
    )

    d = rec.diagnostics
    assert d["weighting_regime"] == "risk_off"
    assert d["weighting_profile_source"] == "calibration.v1"
    assert d["symbol_families"]["XLE"] == "sector_etf"
    assert d["symbol_families"]["GLD"] == "metals"
    assert d["effective_utility_weights_by_symbol"]["XLE"] == {
        "c": 0.45,
        "h1": 0.25,
        "h5": 0.30,
    }
    assert d["effective_utility_weights_by_symbol"]["GLD"] == {
        "c": 0.35,
        "h1": 0.20,
        "h5": 0.45,
    }
    assert abs(d["held_components"]["XLE"]["blend"] - 0.585) < 1e-9
    assert abs(d["candidate_components"]["GLD"]["blend"] - 0.545) < 1e-9
