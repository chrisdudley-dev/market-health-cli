"""
forecast_checks_c_crowding.py

Forecast-mode Dimension C (Crowding) checks — exactly 6 checks.
Horizon-aware version so H1 vs H5 can produce meaningfully different scores.
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
            horizon_days=horizon_days,
            corr20=corr20,
            dispersion=dispersion,
        ),
    ]


def c1_extension_risk(*, horizon_days: int, ext_z_20: Optional[float]) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is the move too far too fast, increasing mean reversion risk into H?"

    if ext_z_20 is None:
        return neutral_check(
            "Extension Risk", meaning, "Insufficient history; neutral."
        )

    warn_z = 1.60 - 0.25 * (h_scale - 1.0)
    danger_z = 2.35 - 0.35 * (h_scale - 1.0)

    if ext_z_20 >= danger_z:
        sc = 0
    elif ext_z_20 >= warn_z:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Extension Risk",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "ext_z_20": ext_z_20,
            "warn_z_threshold": warn_z,
            "danger_z_threshold": danger_z,
        },
    )


def c2_volume_climax_risk(
    *,
    horizon_days: int,
    vol_rank_20: Optional[float],
    last_ret: Optional[float],
    clv: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Did a volume climax likely mark distribution or instability into H?"

    if vol_rank_20 is None or last_ret is None:
        return neutral_check(
            "Volume Climax Risk",
            meaning,
            "No volume feed or insufficient history; neutral.",
        )

    clv_val = clv if clv is not None else 0.0
    warn_vol = 0.90 - 0.02 * (h_scale - 1.0)
    danger_vol = 0.95 - 0.03 * (h_scale - 1.0)
    weak_clv = -0.05 * h_scale

    if vol_rank_20 >= danger_vol and (last_ret < 0.0 or clv_val <= weak_clv):
        sc = 0
    elif vol_rank_20 >= warn_vol and (last_ret <= 0.0 or clv_val <= 0.0):
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Volume Climax Risk",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "vol_rank_20": vol_rank_20,
            "last_ret": last_ret,
            "clv": clv,
            "warn_vol_threshold": warn_vol,
            "danger_vol_threshold": danger_vol,
            "weak_clv_threshold": weak_clv,
        },
    )


def c3_breadth_thinning(
    *,
    horizon_days: int,
    returns: Optional[Sequence[Optional[float]]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    lookback = max(15, min(25, 15 + H))
    meaning = "Is participation narrowing (few big days dominate), increasing fragility into H?"

    if returns is None or len(returns) < lookback + 5:
        return neutral_check(
            "Breadth Thinning", meaning, "Insufficient returns history; neutral."
        )

    w = [abs(r) for r in returns[-lookback:] if r is not None]
    if len(w) < max(10, lookback - 3):
        return neutral_check(
            "Breadth Thinning", meaning, "Insufficient usable returns window; neutral."
        )

    total = sum(w)
    top3 = sum(sorted(w, reverse=True)[:3])
    ratio = (top3 / total) if total > 0 else 0.0

    warn_ratio = 0.40 - 0.03 * (h_scale - 1.0)
    danger_ratio = 0.54 - 0.04 * (h_scale - 1.0)

    if ratio >= danger_ratio:
        sc = 0
    elif ratio >= warn_ratio:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Breadth Thinning",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "lookback": lookback,
            "top3_absret_share": ratio,
            "warn_ratio_threshold": warn_ratio,
            "danger_ratio_threshold": danger_ratio,
        },
    )


def c4_flow_pressure(
    *,
    horizon_days: int,
    up_down_vol_ratio_20: Optional[float],
    clv: Optional[float],
    flow_metrics: Optional[Dict[str, float]] = None,
    flow_status: Optional[str] = None,
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Are flows likely to force continuation or reversal (accumulation vs distribution proxy)?"

    fm = flow_metrics
    fs = flow_status
    u = up_down_vol_ratio_20
    clv_val = float(clv) if isinstance(clv, (int, float)) else 0.0

    if fs == "ok" and isinstance(fm, dict) and fm:
        cpr = fm.get("call_put_ratio")
        net = fm.get("net_premium")
        oi = fm.get("oi_change")

        bull_cpr = 1.03 + 0.03 * (h_scale - 1.0)
        bear_cpr = 0.97 - 0.03 * (h_scale - 1.0)
        strong_oi = 0.04 + 0.02 * (h_scale - 1.0)

        bullish = (net is not None and net > 0) or (cpr is not None and cpr >= bull_cpr)
        bearish = (net is not None and net < 0) or (cpr is not None and cpr <= bear_cpr)
        crowded = oi is not None and abs(float(oi)) >= strong_oi

        if bullish and not bearish and not crowded:
            sc = 2
        elif bearish and not bullish:
            sc = 0
        else:
            sc = 1

        return ForecastCheck(
            "Flow Pressure",
            meaning,
            sc,
            {
                "H": H,
                "horizon_scale": h_scale,
                "note": "used flow.v1 (call_put_ratio/net_premium/oi_change where present)",
                "call_put_ratio": cpr,
                "net_premium": net,
                "oi_change": oi,
                "crowded": crowded,
                "bull_cpr_threshold": bull_cpr,
                "bear_cpr_threshold": bear_cpr,
                "strong_oi_threshold": strong_oi,
                "flow_status": fs,
            },
            source_quality="direct",
            fallback_used=False,
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

    strong_up = 1.15 + 0.12 * (h_scale - 1.0)
    ok_up = 1.00 + 0.05 * (h_scale - 1.0)
    strong_clv = 0.15 + 0.08 * (h_scale - 1.0)
    ok_clv = -0.05

    if u >= strong_up and clv_val >= strong_clv:
        sc = 2
    elif u >= ok_up and clv_val >= ok_clv:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Flow Pressure",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "note": proxy_note,
            "up_down_vol_ratio_20": u,
            "clv": clv,
            "strong_up_threshold": strong_up,
            "ok_up_threshold": ok_up,
            "strong_clv_threshold": strong_clv,
            "ok_clv_threshold": ok_clv,
            "flow_status": fs,
        },
        source_quality="proxy",
        fallback_used=True,
    )


def c5_positioning_asymmetry(
    *,
    horizon_days: int,
    returns: Optional[Sequence[Optional[float]]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    lookback = max(15, min(25, 15 + H))
    meaning = "Is behavior one-sided (downside tail skew), so small shocks can cause outsized moves?"

    if returns is None or len(returns) < lookback + 10:
        return neutral_check(
            "Positioning Asymmetry", meaning, "Insufficient returns history; neutral."
        )

    w = [r for r in returns[-lookback:] if r is not None]
    if len(w) < max(10, lookback - 3):
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

    warn_freq = 0.05 - 0.01 * (h_scale - 1.0)
    danger_freq = 0.10 - 0.02 * (h_scale - 1.0)

    if freq >= danger_freq:
        sc = 0
    elif freq >= warn_freq:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Positioning Asymmetry",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "lookback": lookback,
            "downside_tail_freq": freq,
            "sd": sd,
            "warn_freq_threshold": warn_freq,
            "danger_freq_threshold": danger_freq,
        },
    )


def c6_correlation_crowding(
    *, horizon_days: int, corr20: Optional[float], dispersion: Optional[float]
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is the trade crowded into the same tape (high correlation, low dispersion), raising reversal risk?"

    if corr20 is None or dispersion is None:
        return neutral_check(
            "Correlation Crowding",
            meaning,
            "Insufficient correlation/dispersion inputs; neutral.",
        )

    warn_corr = 0.68 - 0.04 * (h_scale - 1.0)
    danger_corr = 0.82 - 0.05 * (h_scale - 1.0)
    warn_disp_max = 0.0095 + 0.0010 * (h_scale - 1.0)
    danger_disp_max = 0.0075 + 0.0012 * (h_scale - 1.0)

    high_corr = corr20 >= danger_corr
    med_corr = corr20 >= warn_corr
    thin_disp = dispersion <= danger_disp_max
    soft_thin_disp = dispersion <= warn_disp_max

    if high_corr and thin_disp:
        sc = 0
    elif med_corr or soft_thin_disp:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Correlation Crowding",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "corr20": corr20,
            "dispersion": dispersion,
            "warn_corr_threshold": warn_corr,
            "danger_corr_threshold": danger_corr,
            "warn_disp_max_threshold": warn_disp_max,
            "danger_disp_max_threshold": danger_disp_max,
            "high_corr": high_corr,
            "med_corr": med_corr,
            "thin_disp": thin_disp,
            "soft_thin_disp": soft_thin_disp,
        },
    )
