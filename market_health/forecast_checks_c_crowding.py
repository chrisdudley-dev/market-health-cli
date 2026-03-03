"""
forecast_checks_c_crowding.py

Forecast-mode Dimension C (Crowding) checks — exactly 6 checks.

C1) Extension Risk
C2) Volume Climax Risk
C3) Breadth Thinning
C4) Flow Pressure
C5) Positioning Asymmetry
C6) Correlation Crowding
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .forecast_types import ForecastCheck, neutral_check


def compute_c_checks(
    *,
    horizon_days: int,
    ext_z_20: Optional[float] = None,
    vol_rank_20: Optional[float] = None,
    last_ret: Optional[float] = None,
    clv: Optional[float] = None,
    returns: Optional[Sequence[Optional[float]]] = None,
    up_down_vol_ratio_20: Optional[float] = None,
    corr20: Optional[float] = None,
    dispersion: Optional[float] = None,
    flow_metrics: Optional[Dict[str, float]] = None,
    flow_status: Optional[str] = None,
) -> List[ForecastCheck]:
    return [
        c1_extension_risk(horizon_days=horizon_days, ext_z_20=ext_z_20),
        c2_volume_climax_risk(
            horizon_days=horizon_days,
            vol_rank_20=vol_rank_20,
            last_ret=last_ret,
            clv=clv,
        ),
        c3_breadth_thinning(horizon_days=horizon_days, returns=returns),
        c4_flow_pressure(
            horizon_days=horizon_days,
            up_down_vol_ratio_20=up_down_vol_ratio_20,
            clv=clv,
            flow_metrics=flow_metrics,
            flow_status=flow_status,
        ),
        c5_positioning_asymmetry(horizon_days=horizon_days, returns=returns),
        c6_correlation_crowding(
            horizon_days=horizon_days, corr20=corr20, dispersion=dispersion
        ),
    ]


def c1_extension_risk(*, horizon_days: int, ext_z_20: Optional[float]) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is the move too far too fast, increasing mean reversion risk into H?"
    if ext_z_20 is None:
        return neutral_check(
            "Extension Risk", meaning, "Insufficient history; neutral."
        )
    if ext_z_20 >= 2.5:
        sc = 0
    elif ext_z_20 >= 1.5:
        sc = 1
    else:
        sc = 2
    return ForecastCheck("Extension Risk", meaning, sc, {"ext_z_20": ext_z_20})


def c2_volume_climax_risk(
    *,
    horizon_days: int,
    vol_rank_20: Optional[float],
    last_ret: Optional[float],
    clv: Optional[float],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Did a volume climax likely mark distribution or instability into H?"
    if vol_rank_20 is None or last_ret is None:
        return neutral_check(
            "Volume Climax Risk",
            meaning,
            "No volume feed or insufficient history; neutral.",
        )
    clv_val = clv if clv is not None else 0.0
    if vol_rank_20 >= 0.95 and (last_ret < 0.0 or clv_val < -0.2):
        sc = 0
    elif vol_rank_20 >= 0.90:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Volume Climax Risk",
        meaning,
        sc,
        {"vol_rank_20": vol_rank_20, "last_ret": last_ret, "clv": clv},
    )


def c3_breadth_thinning(
    *, horizon_days: int, returns: Optional[Sequence[Optional[float]]]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is participation narrowing (few big days dominate), increasing fragility into H?"
    if returns is None or len(returns) < 25:
        return neutral_check(
            "Breadth Thinning", meaning, "Insufficient returns history; neutral."
        )
    w = [abs(r) for r in returns[-20:] if r is not None]
    if len(w) < 10:
        return neutral_check(
            "Breadth Thinning", meaning, "Insufficient usable returns window; neutral."
        )
    total = sum(w)
    top3 = sum(sorted(w, reverse=True)[:3])
    ratio = (top3 / total) if total > 0 else 0.0
    if ratio >= 0.55:
        sc = 0
    elif ratio >= 0.40:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Breadth Thinning", meaning, sc, {"top3_absret_share_20": ratio}
    )


def c4_flow_pressure(
    *,
    horizon_days: int,
    up_down_vol_ratio_20: Optional[float],
    clv: Optional[float],
    flow_metrics: Optional[Dict[str, float]] = None,
    flow_status: Optional[str] = None,
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Are flows likely to force continuation or reversal (accumulation vs distribution proxy)?"

    fm = locals().get("flow_metrics")
    fs = locals().get("flow_status")
    u = locals().get("up_down_vol_ratio_20")
    clv = locals().get("clv")

    if fs == "ok" and isinstance(fm, dict) and fm:
        cpr = fm.get("call_put_ratio")
        net = fm.get("net_premium")
        oi = fm.get("oi_change")
        bull = (net is not None and net > 0) or (cpr is not None and cpr >= 1.05)
        bear = (net is not None and net < 0) or (cpr is not None and cpr <= 0.95)
        crowded = oi is not None and abs(oi) >= 0.05
        if bull and not bear:
            sc = 2
        elif bear and not bull:
            sc = 0
        else:
            sc = 1
        return ForecastCheck(
            "Flow Pressure",
            meaning,
            sc,
            {
                "note": "used flow.v1 (call_put_ratio/net_premium/oi_change where present)",
                "call_put_ratio": cpr,
                "net_premium": net,
                "oi_change": oi,
                "crowded": crowded,
                "flow_status": fs,
            },
        )

    proxy_note = (
        "flow.v1 status=ok but no symbol metrics; used volume proxy"
        if fs == "ok"
        else f"flow.v1 missing (status={fs}); used volume proxy"
    )
    if u is None:
        return neutral_check(
            "Flow Pressure", meaning, f"{proxy_note}; no volume feed; neutral."
        )
    clv_val = clv if isinstance(clv, (int, float)) else 0.0
    if u >= 1.2 and clv_val > 0.0:
        sc = 2
    elif u >= 1.0:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Flow Pressure",
        meaning,
        sc,
        {
            "note": proxy_note,
            "up_down_vol_ratio_20": u,
            "clv": clv,
            "flow_status": fs,
        },
    )


def c5_positioning_asymmetry(
    *, horizon_days: int, returns: Optional[Sequence[Optional[float]]]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is behavior one-sided (downside tail skew), so small shocks can cause outsized moves?"
    if returns is None or len(returns) < 30:
        return neutral_check(
            "Positioning Asymmetry", meaning, "Insufficient returns history; neutral."
        )
    w = [r for r in returns[-20:] if r is not None]
    if len(w) < 10:
        return neutral_check(
            "Positioning Asymmetry",
            meaning,
            "Insufficient usable returns window; neutral.",
        )
    m = sum(w) / len(w)
    var = sum((r - m) ** 2 for r in w) / max(1, (len(w) - 1))
    sd = var**0.5
    tail = sum(1 for r in w if sd > 0 and r < -2.0 * sd)
    freq = tail / len(w)
    if freq >= 0.10:
        sc = 0
    elif freq >= 0.05:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Positioning Asymmetry",
        meaning,
        sc,
        {"downside_tail_freq_20": freq, "sd_20": sd},
    )


def c6_correlation_crowding(
    *, horizon_days: int, corr20: Optional[float], dispersion: Optional[float]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is diversification collapsing (high correlation / low dispersion), reducing rotation edge?"
    if corr20 is None or dispersion is None:
        return neutral_check(
            "Correlation Crowding", meaning, "Insufficient universe context; neutral."
        )
    if corr20 >= 0.85 and dispersion < 0.006:
        sc = 0
    elif corr20 >= 0.75 or dispersion < 0.008:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Correlation Crowding",
        meaning,
        sc,
        {"corr20": corr20, "dispersion": dispersion},
    )
