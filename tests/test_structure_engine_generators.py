from math import isclose

from market_health.structure_engine import (
    generate_anchored_vwap_levels,
    generate_atr_band_levels,
    generate_bollinger_band_levels,
    generate_classic_pivot_levels,
    generate_donchian_levels,
    generate_moving_average_levels,
    generate_previous_bar_levels,
    generate_rolling_high_low_levels,
    generate_swing_levels,
)


def _by_label(levels):
    return {level.label: level for level in levels}


def test_generate_previous_bar_levels() -> None:
    levels = _by_label(generate_previous_bar_levels(high=10.0, low=8.0))
    assert levels["prev_low"].value == 8.0
    assert levels["prev_low"].kind == "support"
    assert levels["prev_high"].value == 10.0
    assert levels["prev_high"].kind == "resistance"


def test_generate_rolling_high_low_levels() -> None:
    levels = _by_label(
        generate_rolling_high_low_levels(
            highs=[1, 3, 2, 4, 5],
            lows=[0, -1, 1, 2, 3],
            windows=(3, 5),
        )
    )
    assert levels["rolling_low_3"].value == 1
    assert levels["rolling_high_3"].value == 5
    assert levels["rolling_low_5"].value == -1
    assert levels["rolling_high_5"].value == 5


def test_generate_classic_pivot_levels() -> None:
    levels = _by_label(generate_classic_pivot_levels(high=10.0, low=8.0, close=9.0))
    assert isclose(levels["pivot"].value, 9.0)
    assert isclose(levels["s1"].value, 8.0)
    assert isclose(levels["r1"].value, 10.0)
    assert isclose(levels["s2"].value, 7.0)
    assert isclose(levels["r2"].value, 11.0)


def test_generate_moving_average_levels() -> None:
    levels = _by_label(
        generate_moving_average_levels(
            closes=[1, 2, 3, 4, 5],
            sma_periods=(5,),
            ema_periods=(3,),
        )
    )
    assert isclose(levels["sma_5"].value, 3.0)
    assert isclose(levels["ema_3"].value, 4.0625)


def test_generate_anchored_vwap_levels() -> None:
    levels = _by_label(
        generate_anchored_vwap_levels(
            prices=[10.0, 12.0],
            volumes=[1.0, 3.0],
            anchor_index=0,
        )
    )
    assert isclose(levels["anchored_vwap_0"].value, 11.5)


def test_generate_atr_band_levels() -> None:
    levels = _by_label(
        generate_atr_band_levels(
            price=100.0,
            atr=2.0,
            multiples=(1.0, 2.0),
        )
    )
    assert isclose(levels["atr_lower_1x"].value, 98.0)
    assert isclose(levels["atr_upper_1x"].value, 102.0)
    assert isclose(levels["atr_lower_2x"].value, 96.0)
    assert isclose(levels["atr_upper_2x"].value, 104.0)


def test_generate_swing_levels() -> None:
    levels = _by_label(
        generate_swing_levels(
            highs=[1, 4, 2, 5, 3],
            lows=[3, 1, 2, 0, 4],
            left=1,
            right=1,
        )
    )
    assert levels["swing_high_1"].value == 4
    assert levels["swing_high_3"].value == 5
    assert levels["swing_low_1"].value == 1
    assert levels["swing_low_3"].value == 0


def test_generate_donchian_levels() -> None:
    levels = _by_label(
        generate_donchian_levels(
            highs=[1, 3, 2, 4, 5],
            lows=[0, -1, 1, 2, 3],
            period=5,
        )
    )
    assert levels["donchian_lower_5"].value == -1
    assert levels["donchian_upper_5"].value == 5


def test_generate_bollinger_band_levels() -> None:
    levels = _by_label(
        generate_bollinger_band_levels(
            closes=[1, 2, 3, 4, 5],
            period=5,
            num_std=2.0,
        )
    )
    assert isclose(levels["bollinger_mid_5"].value, 3.0)
    assert isclose(levels["bollinger_lower_5"].value, 0.1715728752538097)
    assert isclose(levels["bollinger_upper_5"].value, 5.82842712474619)
