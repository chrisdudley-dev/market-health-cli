import json

from market_health.dashboard_legacy import _pair_reason_tag, render_reco


def test_pair_reason_tag_covers_live_candidate_side_states():
    from_structure = {
        "support_cushion_atr": 0.7819818086008201,
        "overhead_resistance_atr": 0.0,
        "state_tags": ["overhead_heavy", "breakout_ready"],
    }

    xlu_structure = {
        "support_cushion_atr": 0.5039014442802543,
        "overhead_resistance_atr": 0.0,
        "state_tags": ["overhead_heavy", "breakout_ready"],
    }
    xlk_structure = {
        "support_cushion_atr": 0.16114179573175444,
        "overhead_resistance_atr": 0.0,
        "state_tags": ["near_damage_zone", "overhead_heavy"],
    }
    xlre_structure = {
        "support_cushion_atr": 0.0,
        "overhead_resistance_atr": 0.3050241373145003,
        "state_tags": ["near_damage_zone", "overhead_heavy", "reclaim_ready"],
    }

    assert _pair_reason_tag(from_structure, xlu_structure) == "breakout-ready"
    assert _pair_reason_tag(from_structure, xlk_structure) == "damage risk"
    assert _pair_reason_tag(from_structure, xlre_structure) == "reclaim-ready"


def test_forecast_pair_table_uses_structure_tags_not_veto_shorthand(
    monkeypatch, tmp_path
):
    fs_doc = {
        "schema": "forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "scores": {
            "XLE": {
                "5": {
                    "forecast_score": 0.62,
                    "structure_summary": {
                        "support_cushion_atr": 0.7819818086008201,
                        "overhead_resistance_atr": 0.0,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                }
            },
            "XLU": {
                "5": {
                    "forecast_score": 0.57,
                    "structure_summary": {
                        "support_cushion_atr": 0.5039014442802543,
                        "overhead_resistance_atr": 0.0,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                }
            },
            "XLK": {
                "5": {
                    "forecast_score": 0.52,
                    "structure_summary": {
                        "support_cushion_atr": 0.16114179573175444,
                        "overhead_resistance_atr": 0.0,
                        "state_tags": ["near_damage_zone", "overhead_heavy"],
                    },
                }
            },
            "XLRE": {
                "5": {
                    "forecast_score": 0.50,
                    "structure_summary": {
                        "support_cushion_atr": 0.0,
                        "overhead_resistance_atr": 0.3050241373145003,
                        "state_tags": [
                            "near_damage_zone",
                            "overhead_heavy",
                            "reclaim_ready",
                        ],
                    },
                }
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
                "best_candidate": "XLU",
                "weakest_held": "XLE",
                "selected_pair": {
                    "from_symbol": "XLE",
                    "to_symbol": "XLU",
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
                    {
                        "from_symbol": "XLE",
                        "to_symbol": "XLRE",
                        "from_blend": 0.57,
                        "to_blend": 0.42,
                        "robust_edge": -0.12,
                        "weighted_robust_edge": -0.12,
                        "avg_edge": -0.12,
                        "edges_by_h": {"1": -0.12, "5": -0.12},
                        "vetoed": True,
                        "veto_reason": "disagreement_veto:edge(1,5)<0",
                    },
                ],
                "candidate_rows": [],
            },
        }
    }

    out = render_reco([], {}, rec_doc, ["XLE"])

    assert "Forecast candidate pairs" in out
    assert "breakout-ready" in out
    assert "damage risk" in out
    assert "reclaim-ready" in out
    assert "e15<0" not in out
