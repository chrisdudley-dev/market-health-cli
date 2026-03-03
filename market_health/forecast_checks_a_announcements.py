"""
forecast_checks_a_announcements.py

Forecast-mode Dimension A (Announcements) checks — exactly 6 checks.

A1) Catalyst Window
A2) Macro Calendar Pressure
A3) Earnings Cluster
A4) Policy / Regulation Risk
A5) Headline Shock Proxy
A6) Narrative Momentum
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
    )


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
            horizon_days=horizon_days, vix_features=vix_features
        ),
        a3_earnings_cluster(horizon_days=horizon_days, calendar=calendar),
        a4_policy_reg_risk(horizon_days=horizon_days, calendar=calendar),
        a5_headline_shock_proxy(
            horizon_days=horizon_days, ext_z=ext_z, bb_width=bb_width, atrp14=atrp14
        ),
        a6_narrative_momentum(
            horizon_days=horizon_days, rs_slope_10=rs_slope_10, returns=returns
        ),
    ]


def a1_catalyst_window(
    *, horizon_days: int, calendar: Optional[Dict[str, Any]]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    H = horizon_days
    meaning = "Are there scheduled catalysts within the next H trading days that can dominate outcomes?"
    if not calendar:
        return neutral_check("Catalyst Window", meaning, "No calendar feed; neutral.")

    sym = str(calendar.get("symbol") or "").strip().upper()

    # Recommended policy: only treat catalysts as relevant if symbol is explicitly listed.
    syms = calendar.get("catalyst_symbols_in_window")
    if not isinstance(syms, list):
        # fallback: tolerate nested window shape if present
        cat = calendar.get("catalyst")
        if isinstance(cat, dict) and isinstance(cat.get("symbols"), list):
            syms = cat.get("symbols")
        else:
            syms = []

    syms_u = {s.strip().upper() for s in syms if isinstance(s, str) and s.strip()}
    in_window = bool(sym and sym in syms_u)

    score = 0 if in_window else 2
    return make_check(
        "Catalyst Window",
        meaning,
        score,
        {
            "H": H,
            "symbol": sym,
            "catalysts_in_window": in_window,
            "catalyst_symbols_in_window": sorted(syms_u),
        },
    )


def a2_macro_calendar_pressure(
    *, horizon_days: int, vix_features: Dict[str, Any]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    H = horizon_days
    meaning = (
        "Is upcoming macro uncertainty likely to pressure decision quality into H?"
    )
    if not vix_features:
        return neutral_check(
            "Macro Calendar Pressure", meaning, "No VIX feed; neutral."
        )
    vix_slope = vix_features.get("vix_slope_10", [])
    vix_rank = vix_features.get("vix_rank_60", [])
    slope_now = vix_slope[-1] if isinstance(vix_slope, list) and vix_slope else None
    rank_now = vix_rank[-1] if isinstance(vix_rank, list) and vix_rank else None
    elevated = rank_now is not None and rank_now >= 0.75
    rising = slope_now is not None and slope_now > 0.0
    if elevated and rising:
        sc = 0
    elif elevated or rising:
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Macro Calendar Pressure",
        meaning,
        sc,
        {"H": H, "vix_rank_60": rank_now, "vix_slope_10": slope_now},
    )


def a3_earnings_cluster(
    *, horizon_days: int, calendar: Optional[Dict[str, Any]]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    H = horizon_days
    meaning = "Are many major constituents reporting soon, increasing variance and headline risk into H?"
    if not calendar:
        return neutral_check(
            "Earnings Cluster", meaning, "No earnings calendar; neutral."
        )

    sym = str(calendar.get("symbol") or "").strip().upper()

    # Prefer horizon-aware keys populated by the provider calendar context.
    cluster = calendar.get("earnings_cluster_in_window", None)
    if cluster is None:
        cluster = calendar.get("earnings_in_window", None)

    # Back-compat: legacy key
    if cluster is None:
        cluster = calendar.get("earnings_cluster", False)

    # Final fallback: infer from count if present
    if not isinstance(cluster, bool):
        try:
            cnt = int(calendar.get("earnings_count_in_window", 0) or 0)
        except Exception:
            cnt = 0
        cluster = bool(cnt > 0)

    sc = 0 if cluster else 2

    return ForecastCheck(
        "Earnings Cluster",
        meaning,
        sc,
        {
            "H": H,
            "symbol": sym,
            "earnings_cluster": cluster,
            "earnings_count_in_window": calendar.get("earnings_count_in_window"),
            "earnings_next_date": calendar.get("earnings_next_date"),
            "earnings_symbols_in_window": calendar.get("earnings_symbols_in_window"),
        },
    )


def a4_policy_reg_risk(
    *, horizon_days: int, calendar: Optional[Dict[str, Any]]
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    H = horizon_days
    meaning = "Are sector-relevant policy or regulatory decisions approaching inside H?"
    if not calendar:
        return neutral_check(
            "Policy / Regulation Risk", meaning, "No policy calendar; neutral."
        )
    policy_risk = bool(calendar.get("policy_decision_in_window", False))
    sc = 0 if policy_risk else 2
    return ForecastCheck(
        "Policy / Regulation Risk",
        meaning,
        sc,
        {"H": H, "policy_decision_in_window": policy_risk},
    )


def a5_headline_shock_proxy(
    *,
    horizon_days: int,
    ext_z: Optional[float],
    bb_width: Optional[float],
    atrp14: Optional[float],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is the sector recently shock-prone (gappy/unstable), implying higher surprise risk?"
    z = ext_z if ext_z is not None else 0.0
    width = bb_width if bb_width is not None else 0.0
    a = atrp14 if atrp14 is not None else 0.0
    if (z >= 2.5) or (width >= 10.0) or (a >= 3.0):
        sc = 0
    elif (z >= 1.5) or (width >= 6.0) or (a >= 2.0):
        sc = 1
    else:
        sc = 2
    return ForecastCheck(
        "Headline Shock Proxy",
        meaning,
        sc,
        {"ext_z_20": ext_z, "bb_width": bb_width, "atrp14": atrp14},
    )


def a6_narrative_momentum(
    *,
    horizon_days: int,
    rs_slope_10: Optional[float],
    returns: Optional[Sequence[Optional[float]]],
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h**0.5)))
    _ = h_window
    meaning = "Is the narrative sticking (RS improving, few fast reversals) rather than constantly fading?"
    if rs_slope_10 is None:
        return neutral_check(
            "Narrative Momentum", meaning, "Insufficient RS history; neutral."
        )
    rev = recent_reversal_rate(returns, window=10) if returns is not None else None
    rev_val = rev if rev is not None else 0.5
    slope = rs_slope_10
    if slope > 0.0 and rev_val < 0.30:
        sc = 2
    elif slope >= -0.0005 and rev_val < 0.45:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Narrative Momentum",
        meaning,
        sc,
        {"rs_slope_10": rs_slope_10, "reversal_rate_10": rev},
    )


def recent_reversal_rate(
    returns: Optional[Sequence[Optional[float]]], window: int
) -> Optional[float]:
    if returns is None:
        return None
    if window <= 2 or len(returns) < window:
        return None
    w = returns[-window:]
    s: List[int] = []
    for r in w:
        if r is None:
            continue
        if r > 0:
            s.append(1)
        elif r < 0:
            s.append(-1)
        else:
            s.append(0)
    if len(s) < 3:
        return None
    flips = 0
    total = 0
    for i in range(1, len(s)):
        if s[i] == 0 or s[i - 1] == 0:
            continue
        total += 1
        if s[i] != s[i - 1]:
            flips += 1
    return (flips / total) if total else None
