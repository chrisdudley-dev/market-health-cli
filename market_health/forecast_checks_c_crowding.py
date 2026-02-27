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

from typing import List, Optional, Sequence

from .forecast_types import ForecastCheck, neutral_check


def compute_c_checks(
    *,
    ext_z_20: Optional[float] = None,
    vol_rank_20: Optional[float] = None,
    last_ret: Optional[float] = None,
    clv: Optional[float] = None,
    returns: Optional[Sequence[Optional[float]]] = None,
    up_down_vol_ratio_20: Optional[float] = None,
    corr20: Optional[float] = None,
    dispersion: Optional[float] = None,
) -> List[ForecastCheck]:
    return [
        c1_extension_risk(ext_z_20=ext_z_20),
        c2_volume_climax_risk(vol_rank_20=vol_rank_20, last_ret=last_ret, clv=clv),
        c3_breadth_thinning(returns=returns),
        c4_flow_pressure(up_down_vol_ratio_20=up_down_vol_ratio_20, clv=clv),
        c5_positioning_asymmetry(returns=returns),
        c6_correlation_crowding(corr20=corr20, dispersion=dispersion),
    ]


def c1_extension_risk(*, ext_z_20: Optional[float]) -> ForecastCheck:
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
    *, vol_rank_20: Optional[float], last_ret: Optional[float], clv: Optional[float]
) -> ForecastCheck:
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
    *, returns: Optional[Sequence[Optional[float]]]
) -> ForecastCheck:
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
    *, up_down_vol_ratio_20: Optional[float], clv: Optional[float]
) -> ForecastCheck:
    meaning = "Are flows likely to force continuation or reversal (accumulation vs distribution proxy)?"
    if up_down_vol_ratio_20 is None:
        return neutral_check("Flow Pressure", meaning, "No volume feed; neutral.")
    clv_val = clv if clv is not None else 0.0
    if up_down_vol_ratio_20 >= 1.2 and clv_val > 0.0:
        sc = 2
    elif up_down_vol_ratio_20 >= 1.0:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Flow Pressure",
        meaning,
        sc,
        {"up_down_vol_ratio_20": up_down_vol_ratio_20, "clv": clv},
    )


def c5_positioning_asymmetry(
    *, returns: Optional[Sequence[Optional[float]]]
) -> ForecastCheck:
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
    *, corr20: Optional[float], dispersion: Optional[float]
) -> ForecastCheck:
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
