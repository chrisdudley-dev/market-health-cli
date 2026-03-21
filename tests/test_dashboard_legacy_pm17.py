import json
from market_health.dashboard_legacy import render_reco


def test_render_reco_uses_forecast_candidate_row_symbol_keys(monkeypatch, tmp_path):
    fs_doc = {
        "schema": "forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "scores": {
            "XLE": {
                "1": {
                    "forecast_score": 0.62,
                    "structure_summary": {
                        "support_cushion_atr": 0.78,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                },
                "5": {
                    "forecast_score": 0.62,
                    "structure_summary": {
                        "support_cushion_atr": 0.78,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                },
            },
            "XLU": {
                "1": {
                    "forecast_score": 0.57,
                    "structure_summary": {
                        "support_cushion_atr": 0.50,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                },
                "5": {
                    "forecast_score": 0.57,
                    "structure_summary": {
                        "support_cushion_atr": 0.50,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                },
            },
            "XLK": {
                "1": {
                    "forecast_score": 0.52,
                    "structure_summary": {
                        "support_cushion_atr": 0.16,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["near_damage_zone", "overhead_heavy"],
                    },
                },
                "5": {
                    "forecast_score": 0.52,
                    "structure_summary": {
                        "support_cushion_atr": 0.16,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["near_damage_zone", "overhead_heavy"],
                    },
                },
            },
        },
    }

    cache_dir = tmp_path / ".cache" / "jerboa"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "forecast_scores.v1.json").write_text(
        json.dumps(fs_doc), encoding="utf-8"
    )

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    rec_doc = {
        "recommendation": {
            "action": "NOOP",
            "reason": "Forecast veto: disagreement_veto:edge(1,5)<0",
            "diagnostics": {
                "mode": "forecast",
                "decision_metric": "robust_edge",
                "threshold": 0.12,
                "delta_utility": -0.05,
                "utility_weights": {"c": 0.5, "h1": 0.25, "h5": 0.25},
                "best_candidate": "XLU",
                "weakest_held": "XLE",
                "selected_pair": {
                    "from_symbol": "XLE",
                    "to_symbol": "XLU",
                    "from_blend": 0.57,
                    "to_blend": 0.48,
                    "robust_edge": -0.05,
                    "weighted_robust_edge": -0.05,
                    "avg_edge": -0.05,
                    "edges_by_h": {"1": -0.05, "5": -0.05},
                    "vetoed": True,
                    "veto_reason": "disagreement_veto:edge(1,5)<0",
                },
                "held_components": {
                    "XLE": {
                        "symbol": "XLE",
                        "blend": 0.57,
                        "blended": 0.57,
                        "c": 0.52,
                        "current": 0.52,
                        "h1": 0.62,
                        "h5": 0.62,
                        "support_cushion_atr": 0.78,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    }
                },
                "candidate_components": {
                    "XLU": {
                        "symbol": "XLU",
                        "blend": 0.48,
                        "blended": 0.48,
                        "c": 0.40,
                        "current": 0.40,
                        "h1": 0.57,
                        "h5": 0.57,
                        "support_cushion_atr": 0.50,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                    "XLK": {
                        "symbol": "XLK",
                        "blend": 0.48,
                        "blended": 0.48,
                        "c": 0.45,
                        "current": 0.45,
                        "h1": 0.52,
                        "h5": 0.52,
                        "support_cushion_atr": 0.16,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["near_damage_zone", "overhead_heavy"],
                    },
                },
                "candidate_pairs": [
                    {
                        "from_symbol": "XLE",
                        "to_symbol": "XLU",
                        "from_blend": 0.57,
                        "to_blend": 0.48,
                        "robust_edge": -0.05,
                        "weighted_robust_edge": -0.05,
                        "avg_edge": -0.05,
                        "edges_by_h": {"1": -0.05, "5": -0.05},
                        "vetoed": True,
                        "veto_reason": "disagreement_veto:edge(1,5)<0",
                    },
                    {
                        "from_symbol": "XLE",
                        "to_symbol": "XLK",
                        "from_blend": 0.57,
                        "to_blend": 0.48,
                        "robust_edge": -0.10,
                        "weighted_robust_edge": -0.10,
                        "avg_edge": -0.10,
                        "edges_by_h": {"1": -0.10, "5": -0.10},
                        "vetoed": True,
                        "veto_reason": "disagreement_veto:edge(1,5)<0",
                    },
                ],
                "candidate_rows": [
                    {
                        "symbol": "XLU",
                        "blend": 0.48,
                        "blended": 0.48,
                        "c": 0.40,
                        "current": 0.40,
                        "h1": 0.57,
                        "h5": 0.57,
                        "delta_blend": -0.09,
                        "threshold": 0.12,
                        "status": "BLOCKED",
                        "support_cushion_atr": 0.50,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                        "vetoed": True,
                        "veto_reason": "disagreement_veto:edge(1,5)<0",
                    },
                    {
                        "symbol": "XLK",
                        "blend": 0.48,
                        "blended": 0.48,
                        "c": 0.45,
                        "current": 0.45,
                        "h1": 0.52,
                        "h5": 0.52,
                        "delta_blend": -0.10,
                        "threshold": 0.12,
                        "status": "BLOCKED",
                        "support_cushion_atr": 0.16,
                        "overhead_resistance_atr": 0.00,
                        "state_tags": ["near_damage_zone", "overhead_heavy"],
                        "vetoed": True,
                        "veto_reason": "disagreement_veto:edge(1,5)<0",
                    },
                ],
            },
        }
    }

    out = render_reco([], {}, rec_doc, ["XLE"])

    assert "Forecast candidates" in out
    assert "XLU" in out
    assert "XLK" in out
    assert "XLE" in out
    assert "0.48" in out
    assert "BLOCKED" in out
    assert "ΔBlend" in out


def test_forecast_candidate_row_contract_uses_symbol_and_delta_blend():
    row = {
        "symbol": "XLU",
        "blend": 0.48,
        "blended": 0.48,
        "c": 0.40,
        "h1": 0.57,
        "h5": 0.57,
        "delta_blend": -0.09,
        "status": "BLOCKED",
    }

    assert row["symbol"] == "XLU"
    assert "delta_blend" in row
    assert "sym" not in row
    assert "delta_blended" not in row
