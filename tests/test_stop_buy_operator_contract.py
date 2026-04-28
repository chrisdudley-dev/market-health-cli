from __future__ import annotations

from pathlib import Path

from scripts.validate_stop_buy_levels import select_executable_stop_buy_levels


def test_good_score_does_not_override_executable_stop_loss_math():
    """Scores and rankings are separate from executable Stop/Buy order levels."""

    strong_score_context = {
        "symbol": "EXAMPLE",
        "blend": 0.72,
        "current": 0.63,
        "h1": 0.85,
        "h5": 0.78,
        "standing": "good",
    }

    candidates = [
        {"level": 42.20, "kind": "floor", "source": "swing_low", "weight": 1.0},
        {"level": 42.40, "kind": "floor", "source": "volume_shelf_60d", "weight": 0.9},
        {"level": 45.00, "kind": "ceiling", "source": "swing_high", "weight": 1.0},
        {
            "level": 45.20,
            "kind": "ceiling",
            "source": "rolling_high_20d",
            "weight": 0.85,
        },
    ]

    out = select_executable_stop_buy_levels(
        candidates,
        last_close=43.27,
        atr=1.20,
        recent_low=39.00,
        recent_high=46.00,
    )

    assert strong_score_context["standing"] == "good"

    # The score context is intentionally not passed into Stop/Buy selection.
    assert out["stop_source"] == "clustered_floor"
    assert out["buy_source"] == "clustered_ceiling"

    assert out["stop"] == 41.90
    assert out["buy"] == 45.50
    assert out["stop"] < 43.27
    assert out["buy"] > 43.27


def test_stop_buy_fallback_is_explicit_order_math_not_score_signal():
    candidates = [
        {"level": 42.20, "kind": "floor", "source": "single_floor", "weight": 1.0},
        {"level": 45.20, "kind": "ceiling", "source": "single_ceiling", "weight": 1.0},
    ]

    out = select_executable_stop_buy_levels(
        candidates,
        last_close=43.27,
        atr=1.20,
        recent_low=39.00,
        recent_high=46.00,
    )

    assert out["stop_source"] == "recent_low_atr_fallback"
    assert out["buy_source"] == "recent_high_atr_fallback"
    assert out["stop"] == 38.70
    assert out["buy"] == 46.30


def test_dashboard_remains_simple_without_source_columns():
    source = Path("market_health/dashboard_legacy.py").read_text(encoding="utf-8")

    assert 'tbl.add_column("Stop"' in source
    assert 'tbl.add_column("Buy"' in source
    assert 'tbl.add_column("Stop Source"' not in source
    assert 'tbl.add_column("Buy Source"' not in source
