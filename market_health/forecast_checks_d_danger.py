"""
forecast_checks_d_danger.py

Forecast-mode Dimension D (Danger) checks — exactly 6 checks.
Horizon-aware version so H1 vs H5 can produce meaningfully different scores.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Union

from .forecast_types import ForecastCheck, neutral_check

Number = Union[int, float]


def compute_d_checks(
    *,
    horizon_days: int,
    atrp14: Optional[float] = None,
    atrp_slope_10: Optional[float] = None,
    bb_width: Optional[float] = None,
    returns: Optional[Sequence[Optional[float]]] = None,
    calendar: Optional[Dict[str, any]] = None,
    corr5: Optional[float] = None,
    corr20: Optional[float] = None,
    volume: Optional[Sequence[Number]] = None,
    close: Optional[float] = None,
    lo20: Optional[float] = None,
    support_cushion_proxy: Optional[float] = None,
    iv: Optional[float] = None,
    iv_rank_1y: Optional[float] = None,
    iv_percentile_1y: Optional[float] = None,
    iv_status: Optional[str] = None,
) -> List[ForecastCheck]:
    return [
        d1_volatility_trend(
            horizon_days=horizon_days,
            atrp14=atrp14,
            atrp_slope_10=atrp_slope_10,
            bb_width=bb_width,
            iv=iv,
            iv_rank_1y=iv_rank_1y,
            iv_percentile_1y=iv_percentile_1y,
            iv_status=iv_status,
        ),
        d2_tail_gap_risk(
            horizon_days=horizon_days,
            returns=returns,
            calendar=calendar,
            atrp14=atrp14,
        ),
        d3_market_coupling_trend(
            horizon_days=horizon_days,
            corr5=corr5,
            corr20=corr20,
        ),
        d4_liquidity_stress(
            horizon_days=horizon_days,
            returns=returns,
            volume=volume,
        ),
        d5_drawdown_vulnerability(
            horizon_days=horizon_days,
            close=close,
            lo20=lo20,
            atrp14=atrp14,
        ),
        d6_risk_reward_feasibility(
            horizon_days=horizon_days,
            atrp14=atrp14,
            support_cushion_proxy=support_cushion_proxy,
            corr20=corr20,
        ),
    ]


def d1_volatility_trend(
    *,
    horizon_days: int,
    atrp14: Optional[float],
    atrp_slope_10: Optional[float],
    bb_width: Optional[float],
    iv: Optional[float] = None,
    iv_rank_1y: Optional[float] = None,
    iv_percentile_1y: Optional[float] = None,
    iv_status: Optional[str] = None,
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is risk rising or falling (volatility expanding/contracting) into H?"

    have_atr = (atrp14 is not None) and (atrp_slope_10 is not None)
    have_iv = (iv_status == "ok") and (
        iv is not None or iv_rank_1y is not None or iv_percentile_1y is not None
    )

    if not have_atr and not have_iv and bb_width is None:
        return neutral_check(
            "Volatility Trend", meaning, "Missing ATR/IV/BB inputs; neutral."
        )

    rising_cut = 0.00004 + 0.00005 * (h_scale - 1.0)
    fast_rising_cut = 0.00016 + 0.00010 * (h_scale - 1.0)

    rising = bool(have_atr and float(atrp_slope_10) > rising_cut)
    fast_rising = bool(have_atr and float(atrp_slope_10) > fast_rising_cut)

    atr_warn = 2.10 - 0.35 * (h_scale - 1.0)
    atr_danger = 3.00 - 0.60 * (h_scale - 1.0)

    width_warn = 8.00 - 1.75 * (h_scale - 1.0)
    width_danger = 12.00 - 2.50 * (h_scale - 1.0)

    atr_warm = bool(atrp14 is not None and float(atrp14) >= atr_warn)
    atr_hot = bool(atrp14 is not None and float(atrp14) >= atr_danger)

    width_warm = bool(bb_width is not None and float(bb_width) >= width_warn)
    width_hot = bool(bb_width is not None and float(bb_width) >= width_danger)

    proxy_warm = atr_warm or width_warm
    proxy_hot = atr_hot or width_hot

    iv_metric = None
    if iv_percentile_1y is not None:
        iv_metric = float(iv_percentile_1y)
    elif iv_rank_1y is not None:
        iv_metric = float(iv_rank_1y)

    iv_warn = 0.72 - 0.04 * (h_scale - 1.0)
    iv_danger = 0.84 - 0.05 * (h_scale - 1.0)

    iv_warned = bool(have_iv and iv_metric is not None and iv_metric >= iv_warn)
    iv_elevated = bool(have_iv and iv_metric is not None and iv_metric >= iv_danger)

    if have_iv:
        if iv_elevated and (rising or proxy_hot):
            sc = 0
        elif iv_elevated:
            sc = 0 if H >= 5 else 1
        elif iv_warned and (rising or proxy_hot):
            sc = 1
        elif iv_warned:
            sc = 1 if H >= 5 else 2
        elif proxy_hot and fast_rising:
            sc = 0
        elif proxy_hot:
            sc = 1
        elif proxy_warm and rising:
            sc = 1
        elif proxy_warm:
            sc = 1 if H >= 5 else 2
        elif rising and H >= 5:
            sc = 1
        else:
            sc = 2
        note = "used IV + ATR/BB"
    else:
        if proxy_hot and fast_rising:
            sc = 0
        elif proxy_hot:
            sc = 1
        elif proxy_warm and rising:
            sc = 1
        elif proxy_warm:
            sc = 1 if H >= 5 else 2
        elif rising and H >= 5:
            sc = 1
        else:
            sc = 2

        if iv_status == "ok":
            note = "iv.v1 status=ok but no symbol metrics; used ATR/BB proxies"
        else:
            note = f"iv.v1 missing (status={iv_status}); used ATR/BB proxies"

    return ForecastCheck(
        "Volatility Trend",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "atrp14": atrp14,
            "atrp_slope_10": atrp_slope_10,
            "bb_width": bb_width,
            "iv": iv,
            "iv_rank_1y": iv_rank_1y,
            "iv_percentile_1y": iv_percentile_1y,
            "iv_status": iv_status,
            "rising_cut_threshold": rising_cut,
            "fast_rising_cut_threshold": fast_rising_cut,
            "atr_warn_threshold": atr_warn,
            "atr_danger_threshold": atr_danger,
            "width_warn_threshold": width_warn,
            "width_danger_threshold": width_danger,
            "iv_warn_threshold": iv_warn,
            "iv_danger_threshold": iv_danger,
            "rising": rising,
            "fast_rising": fast_rising,
            "atr_warm": atr_warm,
            "atr_hot": atr_hot,
            "width_warm": width_warm,
            "width_hot": width_hot,
            "proxy_warm": proxy_warm,
            "proxy_hot": proxy_hot,
            "iv_warned": iv_warned,
            "iv_elevated": iv_elevated,
            "note": note,
        },
    )


def d2_tail_gap_risk(
    *,
    horizon_days: int,
    returns: Optional[Sequence[Optional[float]]],
    calendar: Optional[Dict[str, any]],
    atrp14: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is gap/tail risk elevated into H (rare large moves more likely)?"

    if returns is None or len(returns) < 30:
        return neutral_check(
            "Tail / Gap Risk", meaning, "Insufficient returns history; neutral."
        )

    w = [r for r in returns[-20:] if r is not None]
    if len(w) < 10:
        return neutral_check(
            "Tail / Gap Risk", meaning, "Insufficient usable returns window; neutral."
        )

    m = sum(w) / len(w)
    var = sum((r - m) ** 2 for r in w) / max(1, (len(w) - 1))
    sd = var**0.5
    big = sum(1 for r in w if sd > 0 and abs(r) > 2.0 * sd)
    freq = big / len(w)

    catalyst = bool(calendar.get("catalysts_in_window", False)) if calendar else False
    freq_h = 1.0 - (1.0 - float(freq)) ** H

    atr = float(atrp14) if isinstance(atrp14, (int, float)) else 0.0
    atr_h = atr * h_scale

    danger_freq = 0.08
    warn_freq = 0.04
    danger_atr_h = 1.9
    warn_atr_h = 1.2

    if (freq_h >= danger_freq) or (catalyst and atr_h >= danger_atr_h):
        sc = 0
    elif (freq_h >= warn_freq) or catalyst or (atr_h >= warn_atr_h):
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Tail / Gap Risk",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "freq_h": freq_h,
            "atr_h": atr_h,
            "big_move_freq_20": freq,
            "sd_20": sd,
            "catalyst_in_window": catalyst,
            "atrp14": atrp14,
            "warn_freq_threshold": warn_freq,
            "danger_freq_threshold": danger_freq,
            "warn_atr_h_threshold": warn_atr_h,
            "danger_atr_h_threshold": danger_atr_h,
        },
    )


def d3_market_coupling_trend(
    *,
    horizon_days: int,
    corr5: Optional[float],
    corr20: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is market coupling increasing (less diversification, more systemic drawdown risk) into H?"

    if corr5 is None or corr20 is None:
        return neutral_check(
            "Market Coupling Trend",
            meaning,
            "Insufficient correlation history; neutral.",
        )

    rising_gap = 0.05 - 0.01 * (h_scale - 1.0)
    high_corr = 0.84 - 0.04 * (h_scale - 1.0)
    warn_corr = 0.72 - 0.04 * (h_scale - 1.0)

    rising = corr5 > corr20 + rising_gap
    high = corr5 >= high_corr
    warned = corr5 >= warn_corr

    if high and rising:
        sc = 0
    elif high or rising or warned:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Market Coupling Trend",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "corr5": corr5,
            "corr20": corr20,
            "rising_gap_threshold": rising_gap,
            "high_corr_threshold": high_corr,
            "warn_corr_threshold": warn_corr,
            "high": high,
            "warned": warned,
            "rising": rising,
        },
    )


def d4_liquidity_stress(
    *,
    horizon_days: int,
    returns: Optional[Sequence[Optional[float]]],
    volume: Optional[Sequence[Number]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    window = 8 if H <= 1 else 20 if H >= 5 else max(10, H * 3)
    meaning = "Is liquidity deteriorating enough that exits become harder and slippage risk rises into H?"

    if returns is None or volume is None:
        return neutral_check(
            "Liquidity Stress", meaning, "Missing returns or volume history; neutral."
        )

    r = [float(x) for x in returns[-window:] if x is not None]
    v = [float(x) for x in volume[-window:] if x is not None]

    n = min(len(r), len(v))
    if n < max(6, window - 2):
        return neutral_check(
            "Liquidity Stress",
            meaning,
            "Insufficient usable returns/volume window; neutral.",
        )

    r = r[-n:]
    v = v[-n:]

    down_vol = [vol for ret, vol in zip(r, v) if ret < 0]
    up_vol = [vol for ret, vol in zip(r, v) if ret > 0]

    avg_down = (sum(down_vol) / len(down_vol)) if down_vol else 0.0
    avg_up = (sum(up_vol) / len(up_vol)) if up_vol else 0.0
    down_up_ratio = (
        (avg_down / avg_up) if avg_up > 0 else (2.0 if avg_down > 0 else 1.0)
    )

    neg_share = sum(1 for x in r if x < 0) / len(r)
    ret_mean = sum(r) / len(r)
    ret_var = sum((x - ret_mean) ** 2 for x in r) / max(1, len(r) - 1)
    ret_sd = ret_var**0.5

    danger_ratio = 1.15 - 0.08 * (h_scale - 1.0)
    warn_ratio = 1.00 - 0.05 * (h_scale - 1.0)
    danger_neg_share = 0.62 - 0.06 * (h_scale - 1.0)
    warn_neg_share = 0.52 - 0.04 * (h_scale - 1.0)

    if down_up_ratio >= danger_ratio and neg_share >= danger_neg_share:
        sc = 0
    elif down_up_ratio >= warn_ratio or neg_share >= warn_neg_share:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Liquidity Stress",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "window": window,
            "down_up_volume_ratio": down_up_ratio,
            "negative_return_share": neg_share,
            "returns_sd": ret_sd,
            "avg_down_volume": avg_down,
            "avg_up_volume": avg_up,
            "danger_ratio_threshold": danger_ratio,
            "warn_ratio_threshold": warn_ratio,
            "danger_negative_share_threshold": danger_neg_share,
            "warn_negative_share_threshold": warn_neg_share,
        },
    )


def d5_drawdown_vulnerability(
    *,
    horizon_days: int,
    close: Optional[float],
    lo20: Optional[float],
    atrp14: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "How vulnerable is the setup to a damaging pullback or breakdown into H?"

    if close is None or lo20 is None:
        return neutral_check(
            "Drawdown Vulnerability", meaning, "Insufficient history; neutral."
        )

    room_pct = ((close - lo20) / close) * 100.0 if close else 0.0
    atr = float(atrp14) if isinstance(atrp14, (int, float)) and atrp14 > 0 else 1.0
    room_atr = room_pct / atr

    strong_room = 1.80 * h_scale
    ok_room = 0.80 * h_scale

    if room_atr >= strong_room:
        sc = 2
    elif room_atr >= ok_room:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Drawdown Vulnerability",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "close": close,
            "lo20": lo20,
            "room_pct_to_lo20": room_pct,
            "atrp14": atrp14,
            "room_atr": room_atr,
            "strong_room_threshold": strong_room,
            "ok_room_threshold": ok_room,
        },
    )


def d6_risk_reward_feasibility(
    *,
    horizon_days: int,
    atrp14: Optional[float],
    support_cushion_proxy: Optional[float],
    corr20: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is the reward opportunity still feasible relative to risk into H?"

    if support_cushion_proxy is None:
        return neutral_check(
            "Risk/Reward Feasibility",
            meaning,
            "Missing support cushion proxy; neutral.",
        )

    corr = float(corr20) if isinstance(corr20, (int, float)) else 0.5
    atr = float(atrp14) if isinstance(atrp14, (int, float)) else 0.0

    strong_cushion = 1.20 * h_scale
    ok_cushion = 0.55 * h_scale
    high_corr = 0.78 - 0.04 * (h_scale - 1.0)
    warn_corr = 0.66 - 0.04 * (h_scale - 1.0)
    high_atr = 2.80 - 0.20 * (h_scale - 1.0)

    if (
        support_cushion_proxy >= strong_cushion
        and corr <= high_corr
        and atr <= high_atr
    ):
        sc = 2
    elif support_cushion_proxy >= ok_cushion and corr <= warn_corr:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Risk/Reward Feasibility",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "support_cushion_proxy": support_cushion_proxy,
            "corr20": corr20,
            "atrp14": atrp14,
            "strong_cushion_threshold": strong_cushion,
            "ok_cushion_threshold": ok_cushion,
            "high_corr_threshold": high_corr,
            "warn_corr_threshold": warn_corr,
            "high_atr_threshold": high_atr,
        },
    )
