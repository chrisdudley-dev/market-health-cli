from __future__ import annotations

from scripts.validate_stop_buy_levels import select_executable_stop_buy_levels


def test_select_executable_stop_buy_levels_prefers_clusters():
    candidates = [
        {"level": 98.0, "kind": "floor", "source": "swing_low", "weight": 1.0},
        {"level": 98.2, "kind": "floor", "source": "ema_21", "weight": 0.7},
        {"level": 105.0, "kind": "ceiling", "source": "swing_high", "weight": 1.0},
        {
            "level": 105.2,
            "kind": "ceiling",
            "source": "rolling_high_20d",
            "weight": 0.85,
        },
    ]

    out = select_executable_stop_buy_levels(
        candidates,
        last_close=100.0,
        atr=2.0,
        recent_low=90.0,
        recent_high=110.0,
    )

    assert out["stop_source"] == "clustered_floor"
    assert out["buy_source"] == "clustered_ceiling"
    assert out["stop"] == 97.5
    assert out["buy"] == 105.7


def test_select_executable_stop_buy_levels_falls_back_without_clusters():
    candidates = [
        {"level": 98.0, "kind": "floor", "source": "single_floor", "weight": 1.0},
        {"level": 105.0, "kind": "ceiling", "source": "single_ceiling", "weight": 1.0},
    ]

    out = select_executable_stop_buy_levels(
        candidates,
        last_close=100.0,
        atr=2.0,
        recent_low=90.0,
        recent_high=110.0,
    )

    assert out["stop_source"] == "recent_low_atr_fallback"
    assert out["buy_source"] == "recent_high_atr_fallback"
    assert out["stop"] == 89.5
    assert out["buy"] == 110.5
