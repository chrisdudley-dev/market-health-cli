from math import isclose

from market_health.structure_engine import compute_structure_summary


def test_compute_structure_summary_emits_minimal_artifact() -> None:
    summary = compute_structure_summary(
        "XLE",
        context={
            "as_of": "2026-03-21T12:00:00+00:00",
            "price": 104.0,
            "atr": 2.0,
            "realized_vol": 0.02,
            "previous_bar": {"high": 105.0, "low": 103.0, "close": 104.0},
            "highs": [101.0, 102.0, 103.0, 104.0, 105.0],
            "lows": [99.0, 100.0, 101.0, 102.0, 103.0],
            "closes": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volumes": [1.0, 1.0, 1.0, 1.0, 1.0],
            "rolling_windows": (5,),
            "donchian_period": 5,
            "bollinger_period": 5,
            "sma_periods": (5,),
            "ema_periods": (3,),
            "swing_left": 1,
            "swing_right": 1,
            "atr_multiples": (1.0,),
            "zone_width": 0.6,
        },
    )

    assert summary.symbol == "XLE"
    assert summary.as_of == "2026-03-21T12:00:00+00:00"
    assert summary.price == 104.0

    assert summary.nearest_support_zone.lower is not None
    assert summary.nearest_support_zone.upper is not None
    assert summary.nearest_resistance_zone.lower is not None
    assert summary.nearest_resistance_zone.upper is not None

    assert summary.breakout_trigger == summary.nearest_resistance_zone.upper
    assert summary.breakdown_trigger == summary.nearest_support_zone.lower
    assert summary.reclaim_trigger == summary.nearest_support_zone.upper
    assert summary.catastrophic_stop_candidate == summary.nearest_support_zone.lower

    assert summary.support_cushion_atr is not None
    assert summary.overhead_resistance_atr is not None
    assert summary.support_confluence_count is not None
    assert summary.resistance_confluence_count is not None
    assert "raw_levels=" in summary.notes[0]


def test_compute_structure_summary_to_dict_contains_required_keys() -> None:
    summary = compute_structure_summary(
        "XLK",
        context={
            "as_of": "2026-03-21T12:00:00+00:00",
            "price": 100.0,
            "atr": 2.0,
            "realized_vol": 0.02,
            "previous_bar": {"high": 101.0, "low": 99.0, "close": 100.0},
            "highs": [97.0, 98.0, 99.0, 100.0, 101.0],
            "lows": [95.0, 96.0, 97.0, 98.0, 99.0],
            "closes": [96.0, 97.0, 98.0, 99.0, 100.0],
            "volumes": [1.0, 2.0, 3.0, 4.0, 5.0],
            "rolling_windows": (5,),
            "donchian_period": 5,
            "bollinger_period": 5,
            "sma_periods": (5,),
            "ema_periods": (3,),
            "swing_left": 1,
            "swing_right": 1,
            "zone_width": 0.6,
        },
    ).to_dict()

    for key in (
        "version",
        "symbol",
        "as_of",
        "price",
        "nearest_support_zone",
        "nearest_resistance_zone",
        "support_cushion_atr",
        "overhead_resistance_atr",
        "breakout_trigger",
        "breakdown_trigger",
        "reclaim_trigger",
        "breakout_quality_bucket",
        "breakdown_risk_bucket",
        "catastrophic_stop_candidate",
        "state_tags",
    ):
        assert key in summary


def test_compute_structure_summary_resistance_distance_is_positive() -> None:
    summary = compute_structure_summary(
        "SCC",
        context={
            "price": 100.0,
            "atr": 2.0,
            "realized_vol": 0.02,
            "previous_bar": {"high": 102.0, "low": 98.0, "close": 100.0},
            "highs": [98.0, 99.0, 100.0, 101.0, 102.0],
            "lows": [94.0, 95.0, 96.0, 97.0, 98.0],
            "closes": [96.0, 97.0, 98.0, 99.0, 100.0],
            "volumes": [1.0, 1.0, 1.0, 1.0, 1.0],
            "rolling_windows": (5,),
            "donchian_period": 5,
            "bollinger_period": 5,
            "sma_periods": (5,),
            "ema_periods": (3,),
            "swing_left": 1,
            "swing_right": 1,
            "zone_width": 0.6,
        },
    )

    assert (
        summary.overhead_resistance_atr is None
        or summary.overhead_resistance_atr >= 0.0
    )
    assert (
        summary.support_cushion_atr is None
        or summary.support_cushion_atr >= 0.0
        or isclose(summary.support_cushion_atr, 0.0)
    )
