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
    H: int,
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
    structure_support_cushion_atr: Optional[float] = None,
    structure_breakdown_risk_bucket: Optional[int] = None,
) -> List[ForecastCheck]:
    return [
        d1_volatility_trend(
            atrp14=atrp14,
            atrp_slope_10=atrp_slope_10,
            bb_width=bb_width,
            iv=iv,
            iv_rank_1y=iv_rank_1y,
            iv_percentile_1y=iv_percentile_1y,
            iv_status=iv_status,
        ),
        d2_tail_gap_risk(H=H, returns=returns, calendar=calendar, atrp14=atrp14),
        d3_market_coupling_trend(corr5=corr5, corr20=corr20),
        d4_liquidity_stress(returns=returns, volume=volume),
        d5_drawdown_vulnerability(
            close=close,
            lo20=lo20,
            atrp14=atrp14,
            structure_support_cushion_atr=structure_support_cushion_atr,
            structure_breakdown_risk_bucket=structure_breakdown_risk_bucket,
        ),
        d6_risk_reward_feasibility(
            atrp14=atrp14,
            support_cushion_proxy=support_cushion_proxy,
            corr20=corr20,
            structure_support_cushion_atr=structure_support_cushion_atr,
            structure_breakdown_risk_bucket=structure_breakdown_risk_bucket,
        ),
    ]


def d1_volatility_trend(
    *,
    atrp14: Optional[float],
    atrp_slope_10: Optional[float],
    bb_width: Optional[float],
    iv: Optional[float] = None,
    iv_rank_1y: Optional[float] = None,
    iv_percentile_1y: Optional[float] = None,
    iv_status: Optional[str] = None,
) -> ForecastCheck:
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
    H: int,
    returns: Optional[Sequence[Optional[float]]],
    calendar: Optional[Dict[str, Any]],
    atrp14: Optional[float],
) -> ForecastCheck:
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
    atr = atrp14 if atrp14 is not None else 0.0
    if (freq >= 0.10) or (catalyst and atr >= 2.0):
        sc = 0
    elif (freq >= 0.05) or catalyst:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Tail / Gap Risk",
        meaning,
        sc,
        {
            "H": H,
            "big_move_freq_20": freq,
            "sd_20": sd,
            "catalyst_in_window": catalyst,
            "atrp14": atrp14,
        },
    )


def d3_market_coupling_trend(
    *, corr5: Optional[float], corr20: Optional[float]
) -> ForecastCheck:
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
    *, returns: Optional[Sequence[Optional[float]]], volume: Optional[Sequence[Number]]
) -> ForecastCheck:
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
    close: Optional[float] = None,
    lo20: Optional[float] = None,
    atrp14: Optional[float] = None,
    structure_support_cushion_atr: Optional[float] = None,
    structure_breakdown_risk_bucket: Optional[int] = None,
) -> ForecastCheck:
    if (
        structure_support_cushion_atr is not None
        and structure_breakdown_risk_bucket is not None
    ):
        effective_cushion = structure_support_cushion_atr
        bucket = max(0, min(2, int(structure_breakdown_risk_bucket)))

        if bucket >= 2 or effective_cushion < 0.5:
            score = 0
        elif bucket == 1 or effective_cushion < 1.0:
            score = 1
        else:
            score = 2

        return ForecastCheck(
            label="Drawdown Vulnerability",
            meaning="Is the sector close to damage levels where a small drop breaks structure?",
            score=score,
            metrics={
                "effective_cushion": effective_cushion,
                "structure_support_cushion_atr": structure_support_cushion_atr,
                "structure_breakdown_risk_bucket": structure_breakdown_risk_bucket,
            },
        )

    dist_pct_to_20d_low = None
    vuln_proxy = None
    if (
        close is not None
        and lo20 is not None
        and atrp14 is not None
        and close > 0
        and atrp14 > 0
    ):
        dist_pct_to_20d_low = 100.0 * (close - lo20) / close
        vuln_proxy = dist_pct_to_20d_low / atrp14
    if vuln_proxy is None:
        return ForecastCheck(
            label="Drawdown Vulnerability",
            meaning="Is the sector close to damage levels where a small drop breaks structure?",
            score=1,
            metrics={"dist_pct_to_20d_low": None, "atrp14": atrp14, "vuln_proxy": None},
        )

    if vuln_proxy <= 1.0:
        score = 0
    elif vuln_proxy <= 2.0:
        score = 1
    else:
        score = 2

    dist_pct_to_20d_low = None
    if close is not None and lo20 is not None and close > 0:
        dist_pct_to_20d_low = 100.0 * (close - lo20) / close

    return ForecastCheck(
        label="Drawdown Vulnerability",
        meaning="Is the sector close to damage levels where a small drop breaks structure?",
        score=score,
        metrics={
            "dist_pct_to_20d_low": dist_pct_to_20d_low,
            "atrp14": atrp14,
            "vuln_proxy": vuln_proxy,
        },
    )


def d6_risk_reward_feasibility(
    *,
    atrp14: Optional[float] = None,
    support_cushion_proxy: Optional[float] = None,
    corr20: Optional[float] = None,
    structure_support_cushion_atr: Optional[float] = None,
    structure_breakdown_risk_bucket: Optional[int] = None,
) -> ForecastCheck:
    effective_cushion = (
        structure_support_cushion_atr
        if structure_support_cushion_atr is not None
        else support_cushion_proxy
    )

    if (
        structure_support_cushion_atr is not None
        and structure_breakdown_risk_bucket is not None
    ):
        bucket = max(0, min(2, int(structure_breakdown_risk_bucket)))

        if bucket >= 2 or (effective_cushion is not None and effective_cushion < 0.5):
            score = 0
        elif bucket == 1 or (effective_cushion is not None and effective_cushion < 1.0):
            score = 1
        else:
            score = 2

        return ForecastCheck(
            label="Risk/Reward Feasibility",
            meaning="Is there enough room versus nearby damage levels to justify the setup?",
            score=score,
            metrics={
                "atrp14": atrp14,
                "support_cushion_proxy": support_cushion_proxy,
                "effective_cushion": effective_cushion,
                "structure_support_cushion_atr": structure_support_cushion_atr,
                "structure_breakdown_risk_bucket": structure_breakdown_risk_bucket,
                "corr20": corr20,
            },
        )

    if effective_cushion is None:
        return ForecastCheck(
            label="Risk/Reward Feasibility",
            meaning="Is there enough room versus nearby damage levels to justify the setup?",
            score=1,
            metrics={
                "atrp14": atrp14,
                "support_cushion_proxy": support_cushion_proxy,
                "effective_cushion": effective_cushion,
                "corr20": corr20,
            },
        )

    if effective_cushion < 0.5:
        score = 0
    elif effective_cushion < 1.0:
        score = 1
    else:
        score = 2

    return ForecastCheck(
        label="Risk/Reward Feasibility",
        meaning="Is there enough room versus nearby damage levels to justify the setup?",
        score=score,
        metrics={
            "atrp14": atrp14,
            "support_cushion_proxy": support_cushion_proxy,
            "effective_cushion": effective_cushion,
            "corr20": corr20,
        },
    )
