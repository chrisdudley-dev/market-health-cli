import sys
import types

stub = types.ModuleType("market_health.inverse_universe_v1")
stub.load_inverse_pairs = lambda *args, **kwargs: {}
sys.modules.setdefault("market_health.inverse_universe_v1", stub)

from market_health.market_ui import _recommendation_lines_from_contract


def test_recommendation_lines_render_non_us_market_suffix() -> None:
    contract = {
        "summary": {
            "recommendations_status": "ok",
            "symbols_sample_meta": [
                {"symbol": "XLU", "market": "US"},
                {"symbol": "1625.T", "market": "JP"},
            ],
        },
        "data": {
            "sectors": [
                {"symbol": "XLU", "market": "US"},
                {"symbol": "1625.T", "market": "JP"},
            ],
            "recommendations": {
                "recommendation": {
                    "action": "SWAP",
                    "horizon_trading_days": 5,
                    "from_symbol": "XLU",
                    "to_symbol": "1625.T",
                    "diagnostics": {
                        "mode": "forecast",
                        "delta_utility": 0.2,
                        "edge": 0.2,
                        "decision_metric": "robust_edge",
                    },
                }
            },
        },
    }

    lines = _recommendation_lines_from_contract(contract)
    assert any("Swap: XLU -> 1625.T [JP]" in line for line in lines)
