import json

from market_health.dashboard_legacy import render_reco


def test_render_reco_shows_risk_overlay_widget(monkeypatch, tmp_path):
    fs_doc = {
        "schema": "forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "scores": {
            "XLE": {
                "5": {
                    "forecast_score": 0.62,
                    "structure_summary": {
                        "nearest_support_zone": {
                            "lower": 58.07,
                            "center": 58.23,
                            "upper": 58.43,
                            "weight": 2.0,
                        },
                        "nearest_resistance_zone": {
                            "lower": 59.72,
                            "center": 59.72,
                            "upper": 59.72,
                            "weight": 2.0,
                        },
                        "support_cushion_atr": 0.40,
                        "overhead_resistance_atr": 0.00,
                        "catastrophic_stop_candidate": 58.07,
                        "breakdown_trigger": 58.07,
                        "reclaim_trigger": 58.43,
                        "breakout_trigger": 59.72,
                        "tactical_stop_candidate": 58.07,
                        "stop_buy_candidate": 59.72,
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

    assert "Risk Overlay — XLE" in out
    assert "status" in out
    assert "ARMED" in out
    assert "catastrophic stop" in out
    assert "breach level" in out
    assert "58.07" in out
