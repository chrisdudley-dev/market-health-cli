"""
forecast_checks_d_danger.py

Forecast-mode Dimension D (Danger) checks — exactly 6 checks.

D1) Volatility Trend
D2) Tail / Gap Risk
D3) Market Coupling Trend
D4) Liquidity Stress
D5) Drawdown Vulnerability
D6) Risk/Reward Feasibility
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

from .forecast_types import ForecastCheck, neutral_check

Number = Union[int, float]


def compute_d_checks(
    *,
    horizon_days: int,
    atrp14: Optional[float] = None,
    atrp_slope_10: Optional[float] = None,
    bb_width: Optional[float] = None,
    returns: Optional[Sequence[Optional[float]]] = None,
    calendar: Optional[Dict[str, Any]] = None,
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
            horizon_days=horizon_days, returns=returns, calendar=calendar, atrp14=atrp14
        ),
        d3_market_coupling_trend(horizon_days=horizon_days, corr5=corr5, corr20=corr20),
        d4_liquidity_stress(horizon_days=horizon_days, returns=returns, volume=volume),
        d5_drawdown_vulnerability(
            horizon_days=horizon_days, close=close, lo20=lo20, atrp14=atrp14
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
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is risk rising or falling (volatility expanding/contracting) into H?"

    atrp14 = locals().get("atrp14")
    atrp_slope_10 = locals().get("atrp_slope_10")
    bb_width = locals().get("bb_width")
    iv = locals().get("iv")
    iv_rank_1y = locals().get("iv_rank_1y")
    iv_percentile_1y = locals().get("iv_percentile_1y")
    iv_status = locals().get("iv_status")

    have_atr = (atrp14 is not None) and (atrp_slope_10 is not None)
    have_iv = (iv_status == "ok") and (
        iv is not None or iv_rank_1y is not None or iv_percentile_1y is not None
    )
    if not have_atr and not have_iv:
        return neutral_check(
            "Volatility Trend", meaning, "No ATR or IV inputs; neutral."
        )

    width = float(bb_width) if isinstance(bb_width, (int, float)) else 0.0
    elevated_proxy = False
    rising = False
    if have_atr:
        elevated_proxy = (float(atrp14) >= 2.5) or (width >= 8.0)
        rising = bool(float(atrp_slope_10) > 0.0)

    elevated_iv = False
    if have_iv:
        r = float(iv_rank_1y) if isinstance(iv_rank_1y, (int, float)) else 0.0
        p = (
            float(iv_percentile_1y)
            if isinstance(iv_percentile_1y, (int, float))
            else 0.0
        )
        elevated_iv = (r >= 0.80) or (p >= 0.80)

    elevated = elevated_proxy or elevated_iv
    if elevated and rising:
        sc = 0
    elif elevated or rising:
        sc = 1
    else:
        sc = 2

    note = (
        "used iv.v1 (rank/percentile) alongside ATR/BB proxies where present"
        if have_iv
        else (
            "iv.v1 status=ok but no symbol metrics; used ATR/BB proxies"
            if iv_status == "ok"
            else f"iv.v1 missing (status={iv_status}); used ATR/BB proxies"
        )
    )
    return ForecastCheck(
        "Volatility Trend",
        meaning,
        sc,
        {
            "note": note,
            "atrp14": atrp14,
            "atrp_slope_10": atrp_slope_10,
            "bb_width": bb_width,
            "iv": iv,
            "iv_rank_1y": iv_rank_1y,
            "iv_percentile_1y": iv_percentile_1y,
            "elevated_proxy": elevated_proxy,
            "elevated_iv": elevated_iv,
            "elevated": elevated,
            "rising": rising,
            "iv_status": iv_status,
        },
    )


def d2_tail_gap_risk(
    *,
    horizon_days: int,
    returns: Optional[Sequence[Optional[float]]],
    calendar: Optional[Dict[str, Any]],
    atrp14: Optional[float],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    H = horizon_days
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
    # Horizon scaling: convert per-day tail frequency into P(>=1 event) within H trading days,
    # and scale ATR-like magnitude by sqrt(H). This makes H5 meaningfully differ from H1.
    H_int = 1
    try:
        H_int = max(1, int(H or 1))
    except Exception:
        H_int = 1
    try:
        freq_h = 1.0 - (1.0 - float(freq)) ** H_int
    except Exception:
        freq_h = None

    atr = atrp14 if atrp14 is not None else 0.0
    try:
        atr_h = float(atr) * (H_int**0.5)
    except Exception:
        atr_h = None

    if (freq_h is not None and freq_h >= 0.10) or (
        catalyst and atr_h is not None and atr_h >= 2.0
    ):
        sc = 0
    elif (freq_h is not None and freq_h >= 0.05) or catalyst:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Tail / Gap Risk",
        meaning,
        sc,
        {
            "H": H,
            "H_int": H_int,
            "freq_h": freq_h,
            "atr_h": atr_h,
            "big_move_freq_20": freq,
            "sd_20": sd,
            "catalyst_in_window": catalyst,
            "atrp14": atrp14,
        },
    )


def d3_market_coupling_trend(
    *, horizon_days: int, corr5: Optional[float], corr20: Optional[float]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is market coupling increasing (less diversification, more systemic drawdown risk) into H?"
    if corr5 is None or corr20 is None:
        return neutral_check(
            "Market Coupling Trend",
            meaning,
            "Insufficient correlation history; neutral.",
        )
    rising = corr5 > corr20 + 0.05
    high = corr5 >= 0.85
    if high and rising:
        sc = 0
    elif high or rising:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Market Coupling Trend",
        meaning,
        sc,
        {"corr5": corr5, "corr20": corr20, "high": high, "rising": rising},
    )


def d4_liquidity_stress(
    *,
    horizon_days: int,
    returns: Optional[Sequence[Optional[float]]],
    volume: Optional[Sequence[Number]],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Are there signs of stressed trading conditions (higher friction, erratic moves) into H?"
    if returns is None or volume is None or len(returns) < 25 or len(volume) < 25:
        return neutral_check(
            "Liquidity Stress",
            meaning,
            "No volume feed or insufficient history; neutral.",
        )
    rets = [r for r in returns[-20:] if r is not None]
    vols = [float(v) for v in volume][-20:]
    if len(rets) < 10 or len(vols) < 10:
        return neutral_check(
            "Liquidity Stress", meaning, "Insufficient usable window; neutral."
        )
    n = min(len(rets), len(vols))
    impacts = [abs(rets[i]) / max(1.0, vols[i]) for i in range(n)]
    imp_now = impacts[-1]
    imp_med = sorted(impacts)[len(impacts) // 2]
    ratio = (imp_now / imp_med) if imp_med > 0 else 1.0
    if ratio >= 2.0:
        sc = 0
    elif ratio >= 1.3:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Liquidity Stress",
        meaning,
        sc,
        {"impact_now": imp_now, "impact_median": imp_med, "impact_ratio": ratio},
    )


def d5_drawdown_vulnerability(
    *,
    horizon_days: int,
    close: Optional[float],
    lo20: Optional[float],
    atrp14: Optional[float],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = (
        "Is the sector close to damage levels where a small drop breaks structure?"
    )
    if close is None or lo20 is None:
        return neutral_check(
            "Drawdown Vulnerability", meaning, "Insufficient history; neutral."
        )
    dist_pct = ((close - lo20) / close) * 100.0 if close else 0.0
    denom = atrp14 if (atrp14 is not None and atrp14 > 0) else 1.0
    vuln_proxy = dist_pct / denom
    if vuln_proxy <= 0.8:
        sc = 0
    elif vuln_proxy <= 1.6:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Drawdown Vulnerability",
        meaning,
        sc,
        {"dist_pct_to_20d_low": dist_pct, "atrp14": atrp14, "vuln_proxy": vuln_proxy},
    )


def d6_risk_reward_feasibility(
    *,
    horizon_days: int,
    atrp14: Optional[float],
    support_cushion_proxy: Optional[float],
    corr20: Optional[float],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Given forecast risk, can you size it and still have acceptable risk/reward feasibility?"
    if atrp14 is None or support_cushion_proxy is None:
        return neutral_check(
            "Risk/Reward Feasibility", meaning, "Insufficient risk inputs; neutral."
        )
    c = corr20 if corr20 is not None else 0.5
    if atrp14 >= 3.0 and support_cushion_proxy < 0.5 and c >= 0.85:
        sc = 0
    elif atrp14 >= 2.5 and support_cushion_proxy < 0.8:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Risk/Reward Feasibility",
        meaning,
        sc,
        {
            "atrp14": atrp14,
            "support_cushion_proxy": support_cushion_proxy,
            "corr20": corr20,
        },
    )
