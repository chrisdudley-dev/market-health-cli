"""
forecast_checks_a_announcements.py

Forecast-mode Dimension A (Announcements) checks — exactly 6 checks.
Horizon-aware version so H1 vs H5 can produce meaningfully different scores.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .forecast_types import ForecastCheck, neutral_check


def make_check(label, meaning, score, metrics):
    """Standard ForecastCheck shape: label/meaning/metrics/score (0/1/2)."""
    try:
        sc = int(score)
    except Exception:
        sc = 1
    if sc < 0:
        sc = 0
    elif sc > 2:
        sc = 2
    return ForecastCheck(
        label=str(label),
        meaning=str(meaning),
        metrics=(metrics or {}),
        score=sc,
        source_quality="proxy",
        fallback_used=False,
    )


def recent_reversal_rate(
    returns: Optional[Sequence[Optional[float]]],
    *,
    window: int = 10,
) -> Optional[float]:
    if returns is None or len(returns) < window:
        return None
    w = [float(r) for r in returns[-window:] if r is not None]
    if len(w) < max(5, window // 2):
        return None

    flips = 0
    for i in range(1, len(w)):
        if w[i - 1] == 0 or w[i] == 0:
            continue
        if (w[i - 1] > 0 and w[i] < 0) or (w[i - 1] < 0 and w[i] > 0):
            flips += 1

    return flips / max(1, len(w) - 1)


def compute_a_checks(
    *,
    horizon_days: int,
    calendar: Optional[Dict[str, Any]] = None,
    vix_features: Optional[Dict[str, Any]] = None,
    ext_z: Optional[float] = None,
    bb_width: Optional[float] = None,
    atrp14: Optional[float] = None,
    rs_slope_10: Optional[float] = None,
    returns: Optional[Sequence[Optional[float]]] = None,
) -> List[ForecastCheck]:
    vix_features = vix_features or {}
    return [
        a1_catalyst_window(horizon_days=horizon_days, calendar=calendar),
        a2_macro_calendar_pressure(
            horizon_days=horizon_days,
            vix_features=vix_features,
        ),
        a3_earnings_cluster(horizon_days=horizon_days, calendar=calendar),
        a4_policy_reg_risk(horizon_days=horizon_days, calendar=calendar),
        a5_headline_shock_proxy(
            horizon_days=horizon_days,
            ext_z=ext_z,
            bb_width=bb_width,
            atrp14=atrp14,
        ),
        a6_narrative_momentum(
            horizon_days=horizon_days,
            rs_slope_10=rs_slope_10,
            returns=returns,
        ),
    ]


def a1_catalyst_window(
    *,
    horizon_days: int,
    calendar: Optional[Dict[str, Any]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Are there scheduled catalysts within the next H trading days that can dominate outcomes?"

    if not calendar:
        return neutral_check("Catalyst Window", meaning, "No calendar feed; neutral.")

    sym = str(calendar.get("symbol") or "").strip().upper()

    syms = calendar.get("catalyst_symbols_in_window")
    if not isinstance(syms, list):
        cat = calendar.get("catalyst")
        if isinstance(cat, dict) and isinstance(cat.get("symbols"), list):
            syms = cat.get("symbols")
        else:
            syms = []

    syms_u = {s.strip().upper() for s in syms if isinstance(s, str) and s.strip()}
    in_window = bool(sym and sym in syms_u)
    catalyst_count = int(calendar.get("catalysts_count_in_window", 0) or 0)

    if in_window and catalyst_count >= max(1, int(round(h_scale))):
        sc = 0
    elif in_window:
        sc = 1
    else:
        sc = 2

    return make_check(
        "Catalyst Window",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "symbol": sym,
            "catalysts_in_window": in_window,
            "catalysts_count_in_window": catalyst_count,
            "catalyst_symbols_in_window": sorted(syms_u),
        },
    )


def a2_macro_calendar_pressure(
    *,
    horizon_days: int,
    vix_features: Dict[str, Any],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = (
        "Is upcoming macro uncertainty likely to pressure decision quality into H?"
    )

    if not vix_features:
        return neutral_check(
            "Macro Calendar Pressure",
            meaning,
            "No VIX feed; neutral.",
        )

    vix_slope = vix_features.get("vix_slope_10", [])
    vix_rank = vix_features.get("vix_rank_60", [])
    slope_now = vix_slope[-1] if isinstance(vix_slope, list) and vix_slope else None
    rank_now = vix_rank[-1] if isinstance(vix_rank, list) and vix_rank else None

    warn_rank = 0.68 - 0.04 * (h_scale - 1.0)
    danger_rank = 0.80 - 0.05 * (h_scale - 1.0)
    warn_slope = -0.00005 * (h_scale - 1.0)

    elevated = rank_now is not None and rank_now >= danger_rank
    caution = rank_now is not None and rank_now >= warn_rank
    rising = slope_now is not None and slope_now > 0.0
    not_falling = slope_now is not None and slope_now >= warn_slope

    if elevated and rising:
        sc = 0
    elif caution and not_falling:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Macro Calendar Pressure",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "vix_rank_60": rank_now,
            "vix_slope_10": slope_now,
            "warn_rank_threshold": warn_rank,
            "danger_rank_threshold": danger_rank,
            "warn_slope_threshold": warn_slope,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def a3_earnings_cluster(
    *,
    horizon_days: int,
    calendar: Optional[Dict[str, Any]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Are many major constituents reporting soon, increasing variance and headline risk into H?"

    if not calendar:
        return neutral_check(
            "Earnings Cluster",
            meaning,
            "No earnings calendar; neutral.",
        )

    sym = str(calendar.get("symbol") or "").strip().upper()
    cluster = calendar.get("earnings_cluster_in_window", None)
    if cluster is None:
        cluster = calendar.get("earnings_in_window", None)
    if cluster is None:
        cluster = calendar.get("earnings_cluster", False)

    try:
        cnt = int(calendar.get("earnings_count_in_window", 0) or 0)
    except Exception:
        cnt = 0

    if not isinstance(cluster, bool):
        cluster = bool(cnt > 0)

    danger_count = 1 if H >= 3 else 2
    if cluster and cnt >= danger_count:
        sc = 0
    elif cluster or cnt > 0:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Earnings Cluster",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "symbol": sym,
            "earnings_cluster": cluster,
            "earnings_count_in_window": cnt,
            "earnings_next_date": calendar.get("earnings_next_date"),
            "earnings_symbols_in_window": calendar.get("earnings_symbols_in_window"),
            "danger_count_threshold": danger_count,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def a4_policy_reg_risk(
    *,
    horizon_days: int,
    calendar: Optional[Dict[str, Any]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Are sector-relevant policy or regulatory decisions approaching inside H?"

    if not calendar:
        return neutral_check(
            "Policy / Regulation Risk",
            meaning,
            "No policy calendar; neutral.",
        )

    policy_risk = bool(calendar.get("policy_decision_in_window", False))

    if policy_risk and H >= 3:
        sc = 0
    elif policy_risk:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Policy / Regulation Risk",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "policy_decision_in_window": policy_risk,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def a5_headline_shock_proxy(
    *,
    horizon_days: int,
    ext_z: Optional[float],
    bb_width: Optional[float],
    atrp14: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is the sector recently shock-prone (gappy/unstable), implying higher surprise risk?"

    z = float(ext_z) if ext_z is not None else 0.0
    width = float(bb_width) if bb_width is not None else 0.0
    atr = float(atrp14) if atrp14 is not None else 0.0

    warn_z = 1.60 - 0.18 * (h_scale - 1.0)
    danger_z = 2.45 - 0.22 * (h_scale - 1.0)
    warn_width = 6.00 - 0.70 * (h_scale - 1.0)
    danger_width = 10.00 - 1.10 * (h_scale - 1.0)
    warn_atr = 2.00 - 0.20 * (h_scale - 1.0)
    danger_atr = 3.00 - 0.30 * (h_scale - 1.0)

    if z >= danger_z or width >= danger_width or atr >= danger_atr:
        sc = 0
    elif z >= warn_z or width >= warn_width or atr >= warn_atr:
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "Headline Shock Proxy",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "ext_z_20": ext_z,
            "bb_width": bb_width,
            "atrp14": atrp14,
            "warn_z_threshold": warn_z,
            "danger_z_threshold": danger_z,
            "warn_width_threshold": warn_width,
            "danger_width_threshold": danger_width,
            "warn_atr_threshold": warn_atr,
            "danger_atr_threshold": danger_atr,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def a6_narrative_momentum(
    *,
    horizon_days: int,
    rs_slope_10: Optional[float],
    returns: Optional[Sequence[Optional[float]]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is the story gaining traction in a way that should persist into H rather than instantly fading?"

    rr = recent_reversal_rate(returns, window=10)
    rs = float(rs_slope_10) if isinstance(rs_slope_10, (int, float)) else 0.0

    if rr is None and rs_slope_10 is None:
        return neutral_check(
            "Narrative Momentum", meaning, "Insufficient RS/return history; neutral."
        )

    reversal = float(rr) if rr is not None else 0.5

    strong_rs = 0.00030 + 0.00010 * (h_scale - 1.0)
    ok_rs = 0.00002 + 0.00005 * (h_scale - 1.0)
    strong_reversal_max = 0.34 - 0.10 * (h_scale - 1.0)
    ok_reversal_max = 0.48 - 0.08 * (h_scale - 1.0)

    if rs >= strong_rs and reversal <= strong_reversal_max:
        sc = 2
    elif rs >= ok_rs and reversal <= ok_reversal_max:
        sc = 1
    elif H <= 2 and rs > 0.0 and reversal <= 0.50:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Narrative Momentum",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "rs_slope_10": rs_slope_10,
            "reversal_rate_10": rr,
            "strong_rs_threshold": strong_rs,
            "ok_rs_threshold": ok_rs,
            "strong_reversal_max": strong_reversal_max,
            "ok_reversal_max": ok_reversal_max,
        },
        source_quality="proxy",
        fallback_used=False,
    )
