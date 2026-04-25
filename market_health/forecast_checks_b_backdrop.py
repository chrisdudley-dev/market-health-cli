"""
forecast_checks_b_backdrop.py

Forecast-mode Dimension B (Backdrop) checks — exactly 6 checks.
Horizon-aware version so H1 vs H5 can produce meaningfully different scores.
"""

from __future__ import annotations

from typing import List, Optional

from .forecast_types import ForecastCheck, neutral_check


def compute_b_checks(
    *,
    horizon_days: int,
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
        b1_trend_persistence(
            horizon_days=horizon_days,
            close=close,
            ema20=ema20,
            sma50=sma50,
            slope_close_10=slope_close_10,
        ),
        b2_follow_through_setup(
            horizon_days=horizon_days,
            close=close,
            hi20=hi20,
            clv=clv,
        ),
        b3_rs_momentum(
            horizon_days=horizon_days,
            rs_slope_10=rs_slope_10,
            rs_z_20=rs_z_20,
        ),
        b4_support_cushion(
            horizon_days=horizon_days,
            close=close,
            ema20=ema20,
            atrp14=atrp14,
        ),
        b5_participation_trend(
            horizon_days=horizon_days,
            up_down_vol_ratio_20=up_down_vol_ratio_20,
            rs_slope_10=rs_slope_10,
        ),
        b6_acceleration_vs_exhaustion(
            horizon_days=horizon_days,
            ext_z_20=ext_z_20,
            slope_close_10=slope_close_10,
            vol_rank_20=vol_rank_20,
        ),
    ]


def b1_trend_persistence(
    *,
    horizon_days: int,
    close: Optional[float],
    ema20: Optional[float],
    sma50: Optional[float],
    slope_close_10: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is the trend likely to persist into H (structure intact and improving)?"
    if close is None or ema20 is None or sma50 is None or slope_close_10 is None:
        return neutral_check(
            "Trend Persistence", meaning, "Insufficient history; neutral."
        )

    up_stack = close > ema20 > sma50
    above_ema = close > ema20
    strong_slope = 0.0005 * h_scale
    ok_slope = 0.0001 * h_scale

    if up_stack and slope_close_10 > strong_slope:
        sc = 2
    elif above_ema and slope_close_10 > ok_slope:
        sc = 1
    elif up_stack and slope_close_10 > 0.0 and H <= 2:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Trend Persistence",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "close": close,
            "ema20": ema20,
            "sma50": sma50,
            "slope_close_10": slope_close_10,
            "up_stack": up_stack,
            "above_ema": above_ema,
            "strong_slope_threshold": strong_slope,
            "ok_slope_threshold": ok_slope,
        },
    )


def b2_follow_through_setup(
    *,
    horizon_days: int,
    close: Optional[float],
    hi20: Optional[float],
    clv: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "If a move just occurred, is it likely to follow through rather than fail quickly?"
    if close is None or hi20 is None:
        return neutral_check(
            "Follow-Through Setup", meaning, "Insufficient history; neutral."
        )

    breakout_pct = ((close / hi20) - 1.0) * 100.0 if hi20 else 0.0
    clv_val = clv if clv is not None else 0.0

    strong_breakout = 0.10
    near_breakout = -1.25 * h_scale
    strong_clv = 0.25 + 0.05 * (h_scale - 1.0)
    ok_clv = 0.10

    if breakout_pct >= strong_breakout and clv_val >= strong_clv:
        sc = 2
    elif breakout_pct >= near_breakout and clv_val >= ok_clv:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Follow-Through Setup",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "close": close,
            "hi20": hi20,
            "breakout_pct": breakout_pct,
            "clv": clv,
            "strong_breakout_threshold": strong_breakout,
            "near_breakout_threshold": near_breakout,
            "strong_clv_threshold": strong_clv,
            "ok_clv_threshold": ok_clv,
        },
    )


def b3_rs_momentum(
    *,
    horizon_days: int,
    rs_slope_10: Optional[float],
    rs_z_20: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is relative strength improving (momentum), not just currently high?"
    if rs_slope_10 is None:
        return neutral_check(
            "RS Momentum vs SPY", meaning, "Insufficient RS history; neutral."
        )

    z = rs_z_20 if rs_z_20 is not None else 0.0
    strong_rs = 0.0004 * h_scale
    ok_rs = 0.00005 * h_scale
    max_good_z = 2.6 - 0.2 * (h_scale - 1.0)

    if rs_slope_10 > strong_rs and z < max_good_z:
        sc = 2
    elif rs_slope_10 > ok_rs:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "RS Momentum vs SPY",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "rs_slope_10": rs_slope_10,
            "rs_z_20": rs_z_20,
            "strong_rs_threshold": strong_rs,
            "ok_rs_threshold": ok_rs,
            "max_good_z_threshold": max_good_z,
        },
    )


def b4_support_cushion(
    *,
    horizon_days: int,
    close: Optional[float],
    ema20: Optional[float],
    atrp14: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "How much room exists before key support breaks (buffer against normal pullbacks)?"
    if close is None or ema20 is None:
        return neutral_check(
            "Support Cushion", meaning, "Insufficient history; neutral."
        )

    dist_pct = ((close - ema20) / close) * 100.0 if close else 0.0
    denom = atrp14 if (atrp14 is not None and atrp14 > 0) else 1.0
    cushion_proxy = dist_pct / denom

    strong_cushion = 1.80 + 0.50 * (h_scale - 1.0)
    ok_cushion = 0.40 + 0.30 * (h_scale - 1.0)

    if cushion_proxy >= strong_cushion:
        sc = 2
    elif cushion_proxy >= ok_cushion:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Support Cushion",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "dist_pct_to_ema20": dist_pct,
            "atrp14": atrp14,
            "cushion_proxy": cushion_proxy,
            "strong_cushion_threshold": strong_cushion,
            "ok_cushion_threshold": ok_cushion,
        },
    )


def b5_participation_trend(
    *,
    horizon_days: int,
    up_down_vol_ratio_20: Optional[float],
    rs_slope_10: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = (
        "Is participation improving (more supportive flow/volume behavior), not fading?"
    )

    if up_down_vol_ratio_20 is None or rs_slope_10 is None:
        return neutral_check(
            "Participation Trend",
            meaning,
            "Insufficient participation history; neutral.",
        )

    ratio = float(up_down_vol_ratio_20)
    rs = float(rs_slope_10)

    strong_ratio = 1.16 + 0.05 * (h_scale - 1.0)
    ok_ratio = 1.01 + 0.03 * (h_scale - 1.0)

    strong_rs = 0.00008 + 0.00008 * (h_scale - 1.0)
    ok_rs = -0.00002 + 0.00005 * (h_scale - 1.0)

    # H1-only early-thrust allowance:
    # strong participation can earn a 1 before RS fully confirms,
    # but only if RS is not deeply negative.
    early_rs_floor = -0.00045 + 0.00008 * (h_scale - 1.0)

    if ratio >= strong_ratio and rs >= strong_rs:
        sc = 2
    elif ratio >= ok_ratio and rs >= ok_rs:
        sc = 1
    elif H <= 2 and ratio >= strong_ratio and rs >= early_rs_floor:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Participation Trend",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "up_down_vol_ratio_20": ratio,
            "rs_slope_10": rs,
            "strong_ratio_threshold": strong_ratio,
            "ok_ratio_threshold": ok_ratio,
            "strong_rs_threshold": strong_rs,
            "ok_rs_threshold": ok_rs,
            "early_rs_floor_threshold": early_rs_floor,
        },
    )


def b6_acceleration_vs_exhaustion(
    *,
    horizon_days: int,
    ext_z_20: Optional[float],
    slope_close_10: Optional[float],
    vol_rank_20: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = (
        "Is momentum accelerating cleanly, or showing exhaustion (late-stage, fragile)?"
    )
    if ext_z_20 is None or slope_close_10 is None:
        return neutral_check(
            "Acceleration vs Exhaustion", meaning, "Insufficient history; neutral."
        )

    v = vol_rank_20 if vol_rank_20 is not None else 0.5

    strong_slope = 0.00045 * h_scale
    clean_ext_max = 1.20 - 0.10 * (h_scale - 1.0)
    ok_ext_max = 2.20 - 0.25 * (h_scale - 1.0)
    clean_vol_max = 0.75 - 0.05 * (h_scale - 1.0)

    if (
        slope_close_10 >= strong_slope
        and ext_z_20 <= clean_ext_max
        and v <= clean_vol_max
    ):
        sc = 2
    elif slope_close_10 > 0.0 and ext_z_20 <= ok_ext_max:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Acceleration vs Exhaustion",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "ext_z_20": ext_z_20,
            "slope_close_10": slope_close_10,
            "vol_rank_20": vol_rank_20,
            "strong_slope_threshold": strong_slope,
            "clean_ext_max_threshold": clean_ext_max,
            "ok_ext_max_threshold": ok_ext_max,
            "clean_vol_max_threshold": clean_vol_max,
        },
    )
