import json

from market_health.dashboard_legacy import render_reco


def test_render_reco_shows_execution_guidance_widget(monkeypatch, tmp_path):
    fs_doc = {
        "schema": "forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "scores": {
            "XLE": {
                "5": {
                    "forecast_score": 0.62,
                    "structure_summary": {
                        "nearest_support_zone": {
                            "lower": 82.10,
                            "center": 82.60,
                            "upper": 83.00,
                            "weight": 2.0,
                        },
                        "nearest_resistance_zone": {
                            "lower": 88.40,
                            "center": 88.90,
                            "upper": 89.30,
                            "weight": 2.0,
                        },
                        "support_cushion_atr": 0.78,
                        "overhead_resistance_atr": 0.00,
                        "breakout_trigger": 89.30,
                        "breakdown_trigger": 82.10,
                        "reclaim_trigger": 83.00,
                        "tactical_stop_candidate": 82.10,
                        "stop_buy_candidate": 89.30,
                        "state_tags": ["overhead_heavy", "breakout_ready"],
                    },
                }
            }
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
                "candidate_pairs": [],
                "candidate_rows": [],
            },
        }
    }

    out = render_reco([], {}, rec_doc, ["XLE"])

    assert "Optional Execution Guidance — XLE" in out
    assert "tactical stop" in out
    assert "stop-buy" in out
    assert "82.10" in out
    assert "89.30" in out
