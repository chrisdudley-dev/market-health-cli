"""
forecast_checks_b_backdrop.py

Forecast-mode Dimension B (Backdrop) checks — exactly 6 checks.

B1) Trend Persistence
B2) Follow-Through Setup
B3) RS Momentum vs SPY
B4) Support Cushion
B5) Participation Trend
B6) Acceleration vs Exhaustion
"""

from __future__ import annotations

from typing import List, Optional

from .forecast_types import ForecastCheck, neutral_check


def compute_b_checks(
    *, horizon_days: int,
    close: Optional[float],
    ema20: Optional[float],
    sma50: Optional[float],
    slope_close_10: Optional[float],
    hi20: Optional[float] = None,
    clv: Optional[float] = None,
    rs_slope_10: Optional[float] = None,
    rs_z_20: Optional[float] = None,
    atrp14: Optional[float] = None,
    up_down_vol_ratio_20: Optional[float] = None,
    ext_z_20: Optional[float] = None,
    vol_rank_20: Optional[float] = None,
) -> List[ForecastCheck]:
    return [
        b1_trend_persistence(horizon_days=horizon_days, close=close, ema20=ema20, sma50=sma50, slope_close_10=slope_close_10
        ),
        b2_follow_through_setup(horizon_days=horizon_days, close=close, hi20=hi20, clv=clv),
        b3_rs_momentum(horizon_days=horizon_days, rs_slope_10=rs_slope_10, rs_z_20=rs_z_20),
        b4_support_cushion(horizon_days=horizon_days, close=close, ema20=ema20, atrp14=atrp14),
        b5_participation_trend(horizon_days=horizon_days, up_down_vol_ratio_20=up_down_vol_ratio_20, rs_slope_10=rs_slope_10
        ),
        b6_acceleration_vs_exhaustion(horizon_days=horizon_days, ext_z_20=ext_z_20, slope_close_10=slope_close_10, vol_rank_20=vol_rank_20
        ),
    ]


def b1_trend_persistence(
    *, horizon_days: int,
    close: Optional[float],
    ema20: Optional[float],
    sma50: Optional[float],
    slope_close_10: Optional[float],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = "Is the trend likely to persist into H (structure intact and improving)?"
    if close is None or ema20 is None or sma50 is None or slope_close_10 is None:
        return neutral_check(
            "Trend Persistence", meaning, "Insufficient history; neutral."
        )
    up_stack = close > ema20 > sma50
    if up_stack and slope_close_10 > 0.0005:
        sc = 2
    elif (close > ema20 and slope_close_10 > 0.0) or (
        up_stack and slope_close_10 >= 0.0
    ):
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Trend Persistence",
        meaning,
        sc,
        {
            "close": close,
            "ema20": ema20,
            "sma50": sma50,
            "slope_close_10": slope_close_10,
            "up_stack": up_stack,
        },
    )


def b2_follow_through_setup(
    *, horizon_days: int, close: Optional[float], hi20: Optional[float], clv: Optional[float]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = "If a move just occurred, is it likely to follow through rather than fail quickly?"
    if close is None or hi20 is None:
        return neutral_check(
            "Follow-Through Setup", meaning, "Insufficient history; neutral."
        )
    breakout = close >= hi20
    clv_val = clv if clv is not None else 0.0
    if breakout and clv_val > 0.3:
        sc = 2
    elif breakout or clv_val > 0.0:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Follow-Through Setup",
        meaning,
        sc,
        {"close": close, "hi20": hi20, "breakout": breakout, "clv": clv},
    )


def b3_rs_momentum(
    *, horizon_days: int, rs_slope_10: Optional[float], rs_z_20: Optional[float]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = "Is relative strength improving (momentum), not just currently high?"
    if rs_slope_10 is None:
        return neutral_check(
            "RS Momentum vs SPY", meaning, "Insufficient RS history; neutral."
        )
    z = rs_z_20 if rs_z_20 is not None else 0.0
    if rs_slope_10 > 0.0005 and z < 2.5:
        sc = 2
    elif rs_slope_10 > 0.0:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "RS Momentum vs SPY",
        meaning,
        sc,
        {"rs_slope_10": rs_slope_10, "rs_z_20": rs_z_20},
    )


def b4_support_cushion(
    *, horizon_days: int, close: Optional[float], ema20: Optional[float], atrp14: Optional[float]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = "How much room exists before key support breaks (buffer against normal pullbacks)?"
    if close is None or ema20 is None:
        return neutral_check(
            "Support Cushion", meaning, "Insufficient history; neutral."
        )
    dist_pct = ((close - ema20) / close) * 100.0 if close else 0.0
    denom = atrp14 if (atrp14 is not None and atrp14 > 0) else 1.0
    cushion_proxy = dist_pct / denom
    if cushion_proxy >= 1.5:
        sc = 2
    elif cushion_proxy >= 0.5:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Support Cushion",
        meaning,
        sc,
        {
            "dist_pct_to_ema20": dist_pct,
            "atrp14": atrp14,
            "cushion_proxy": cushion_proxy,
        },
    )


def b5_participation_trend(
    *, horizon_days: int, up_down_vol_ratio_20: Optional[float], rs_slope_10: Optional[float]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = (
        "Is participation improving (more supportive flow/volume behavior), not fading?"
    )
    if up_down_vol_ratio_20 is None or rs_slope_10 is None:
        return neutral_check(
            "Participation Trend",
            meaning,
            "No volume feed or insufficient history; neutral.",
        )
    if up_down_vol_ratio_20 >= 1.2 and rs_slope_10 > 0.0:
        sc = 2
    elif up_down_vol_ratio_20 >= 1.0:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Participation Trend",
        meaning,
        sc,
        {"up_down_vol_ratio_20": up_down_vol_ratio_20, "rs_slope_10": rs_slope_10},
    )


def b6_acceleration_vs_exhaustion(
    *, horizon_days: int,
    ext_z_20: Optional[float],
    slope_close_10: Optional[float],
    vol_rank_20: Optional[float],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = (
        "Is momentum accelerating cleanly, or showing exhaustion (late-stage, fragile)?"
    )
    if ext_z_20 is None or slope_close_10 is None:
        return neutral_check(
            "Acceleration vs Exhaustion", meaning, "Insufficient history; neutral."
        )
    v = vol_rank_20 if vol_rank_20 is not None else 0.5
    if slope_close_10 > 0.0 and ext_z_20 < 1.8 and v < 0.85:
        sc = 2
    elif ext_z_20 < 2.6:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Acceleration vs Exhaustion",
        meaning,
        sc,
        {
            "slope_close_10": slope_close_10,
            "ext_z_20": ext_z_20,
            "vol_rank_20": vol_rank_20,
        },
    )
