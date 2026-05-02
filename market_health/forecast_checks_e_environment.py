"""
forecast_checks_e_environment.py

Forecast-mode Dimension E (Environment) checks — exactly 6 checks.
Horizon-aware version so H1 vs H5 can produce meaningfully different scores.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set

from .forecast_types import ForecastCheck, neutral_check

DEFENSIVE: Set[str] = {"XLU", "XLP", "XLV"}
CYCLICAL: Set[str] = {"XLY", "XLI", "XLF", "XLB", "XLK", "XLC", "XLE", "XLRE"}


def compute_e_checks(
    *,
    horizon_days: int,
    symbol: str,
    spy_slope_10: Optional[float] = None,
    vix_features: Optional[Dict[str, Any]] = None,
    returns_by_symbol: Optional[Dict[str, Sequence[Optional[float]]]] = None,
    dispersion: Optional[float] = None,
    rs_slope_10: Optional[float] = None,
) -> List[ForecastCheck]:
    vix_features = vix_features or {}
    symbol_u = symbol.upper()

    spy_check = e1_spy_outlook(
        horizon_days=horizon_days,
        spy_slope_10=spy_slope_10,
    )
    vix_check = e2_vix_outlook(
        horizon_days=horizon_days,
        vix_features=vix_features,
    )

    return [
        spy_check,
        vix_check,
        e3_leadership_persistence(
            horizon_days=horizon_days,
            symbol=symbol_u,
            returns_by_symbol=returns_by_symbol,
        ),
        e4_breadth_regime(
            horizon_days=horizon_days,
            dispersion=dispersion,
        ),
        e5_cross_regime_pressure(
            horizon_days=horizon_days,
            symbol=symbol_u,
            returns_by_symbol=returns_by_symbol,
        ),
        e6_driver_alignment(
            horizon_days=horizon_days,
            rs_slope_10=rs_slope_10,
            spy_outlook_score=spy_check.score,
            vix_outlook_score=vix_check.score,
        ),
    ]


def e1_spy_outlook(
    *,
    horizon_days: int,
    spy_slope_10: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is the broad market setup improving or deteriorating into H?"

    if spy_slope_10 is None:
        return neutral_check(
            "SPY Outlook", meaning, "Insufficient SPY history; neutral."
        )

    strong_bull = 0.00020 + 0.00018 * (h_scale - 1.0)
    soft_bull = -0.00002 + 0.00008 * (h_scale - 1.0)
    clear_bear = -0.00018 - 0.00004 * (h_scale - 1.0)

    if spy_slope_10 >= strong_bull:
        sc = 2
    elif spy_slope_10 >= soft_bull:
        sc = 1
    elif spy_slope_10 <= clear_bear:
        sc = 0
    else:
        sc = 1

    return ForecastCheck(
        "SPY Outlook",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "spy_slope_10": spy_slope_10,
            "strong_bull_threshold": strong_bull,
            "soft_bull_threshold": soft_bull,
            "clear_bear_threshold": clear_bear,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def e2_vix_outlook(
    *,
    horizon_days: int,
    vix_features: Dict[str, Any],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Is volatility regime likely to rise or fall into H (risk-on vs risk-off pressure)?"

    if not vix_features:
        return neutral_check("VIX Outlook", meaning, "No VIX feed; neutral.")

    vix_slope = vix_features.get("vix_slope_10", [])
    vix_rank = vix_features.get("vix_rank_60", [])
    slope_now = vix_slope[-1] if isinstance(vix_slope, list) and vix_slope else None
    rank_now = vix_rank[-1] if isinstance(vix_rank, list) and vix_rank else None

    warn_rank = 0.68 - 0.04 * (h_scale - 1.0)
    danger_rank = 0.80 - 0.05 * (h_scale - 1.0)
    flat_or_worse_slope = -0.00005 * (h_scale - 1.0)

    if (
        rank_now is not None
        and rank_now >= danger_rank
        and slope_now is not None
        and slope_now > 0.0
    ):
        sc = 0
    elif (
        rank_now is not None
        and rank_now >= warn_rank
        and slope_now is not None
        and slope_now >= flat_or_worse_slope
    ):
        sc = 1
    else:
        sc = 2

    return ForecastCheck(
        "VIX Outlook",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "vix_rank_60": rank_now,
            "vix_slope_10": slope_now,
            "warn_rank_threshold": warn_rank,
            "danger_rank_threshold": danger_rank,
            "flat_or_worse_slope_threshold": flat_or_worse_slope,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def e3_leadership_persistence(
    *,
    horizon_days: int,
    symbol: str,
    returns_by_symbol: Optional[Dict[str, Sequence[Optional[float]]]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    window = max(4, min(8, H + 2))
    meaning = "Are sector ranks stable (leaders staying leaders) or rotating rapidly?"

    if not returns_by_symbol:
        return neutral_check(
            "Leadership Persistence", meaning, "No universe returns; neutral."
        )

    syms = sorted(returns_by_symbol.keys())
    if symbol not in returns_by_symbol:
        return neutral_check(
            "Leadership Persistence", meaning, "Symbol missing from universe; neutral."
        )

    try:
        min_len = min(len(returns_by_symbol[s]) for s in syms)
    except Exception:
        return neutral_check(
            "Leadership Persistence", meaning, "Invalid universe returns; neutral."
        )

    if min_len < window + 1:
        return neutral_check(
            "Leadership Persistence", meaning, "Insufficient history; neutral."
        )

    ranks: List[int] = []
    for t in range(min_len - window, min_len):
        snapshot: List[tuple[str, float]] = []
        for s in syms:
            r = returns_by_symbol[s][t]
            if r is None:
                return neutral_check(
                    "Leadership Persistence",
                    meaning,
                    "Missing returns in window; neutral.",
                )
            snapshot.append((s, float(r)))

        snapshot.sort(key=lambda x: x[1], reverse=True)
        rank = next((i for i, (s, _) in enumerate(snapshot) if s == symbol), None)
        if rank is None:
            return neutral_check(
                "Leadership Persistence", meaning, "Rank lookup failed; neutral."
            )
        ranks.append(rank)

    span = max(ranks) - min(ranks)
    avg_rank = sum(ranks) / len(ranks)

    strong_span = 1 + int(round(0.5 * h_scale))
    ok_span = 3 + int(round(0.5 * h_scale))
    good_avg_rank = 4.0 + 0.5 * (h_scale - 1.0)

    if span <= strong_span and avg_rank <= good_avg_rank:
        sc = 2
    elif span <= ok_span:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Leadership Persistence",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "window": window,
            "ranks_window": ranks,
            "span": span,
            "avg_rank": avg_rank,
            "strong_span_threshold": strong_span,
            "ok_span_threshold": ok_span,
            "good_avg_rank_threshold": good_avg_rank,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def e4_breadth_regime(
    *,
    horizon_days: int,
    dispersion: Optional[float],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = (
        "Is market participation broad or narrow (proxy via cross-sector dispersion)?"
    )

    if dispersion is None:
        return neutral_check("Breadth Regime", meaning, "No dispersion input; neutral.")

    strong_dispersion = 0.0100 / h_scale
    ok_dispersion = 0.0070 / h_scale

    if dispersion >= strong_dispersion:
        sc = 2
    elif dispersion >= ok_dispersion:
        sc = 1
    else:
        sc = 0

    return ForecastCheck(
        "Breadth Regime",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "dispersion": dispersion,
            "strong_dispersion_threshold": strong_dispersion,
            "ok_dispersion_threshold": ok_dispersion,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def _avg_cumret(
    returns_by_symbol: Dict[str, Sequence[Optional[float]]],
    symset: Set[str],
    *,
    window: int,
) -> Optional[float]:
    vals: List[float] = []
    for s in symset:
        series = returns_by_symbol.get(s)
        if series is None or len(series) < window:
            return None
        w = [x for x in series[-window:] if x is not None]
        if len(w) < window:
            return None
        vals.append(sum(float(x) for x in w))
    return (sum(vals) / len(vals)) if vals else None


def e5_cross_regime_pressure(
    *,
    horizon_days: int,
    symbol: str,
    returns_by_symbol: Optional[Dict[str, Sequence[Optional[float]]]],
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    window = 3 if H <= 1 else 8 if H >= 5 else max(4, H + 2)
    meaning = (
        "Are conditions favoring offense or defense (risk-on vs risk-off tilt into H)?"
    )

    if not returns_by_symbol:
        return neutral_check(
            "Cross-Regime Pressure", meaning, "No universe returns; neutral."
        )

    syms = set(returns_by_symbol.keys())
    def_syms = {s for s in DEFENSIVE if s in syms}
    cyc_syms = {s for s in CYCLICAL if s in syms}

    if len(def_syms) < 2 or len(cyc_syms) < 3:
        return neutral_check(
            "Cross-Regime Pressure",
            meaning,
            "Insufficient defensive/cyclical coverage in universe; neutral.",
        )

    def _avg_cumret(symset: Set[str], win: int) -> Optional[float]:
        vals: List[float] = []
        for s in sorted(symset):
            series = returns_by_symbol.get(s)
            if series is None or len(series) < win:
                return None
            w = [x for x in series[-win:] if x is not None]
            if len(w) < win:
                return None
            vals.append(sum(float(x) for x in w))
        return (sum(vals) / len(vals)) if vals else None

    def_ret = _avg_cumret(def_syms, window)
    cyc_ret = _avg_cumret(cyc_syms, window)

    if def_ret is None or cyc_ret is None:
        return neutral_check(
            "Cross-Regime Pressure",
            meaning,
            "Insufficient returns for regime proxy; neutral.",
        )

    spread = float(cyc_ret) - float(def_ret)
    flat_band = 0.0035 * h_scale
    is_def = symbol in def_syms

    if abs(spread) <= flat_band:
        sc = 1
        regime = "mixed"
    elif spread > flat_band:
        sc = 0 if is_def else 2
        regime = "risk_on"
    else:
        sc = 2 if is_def else 0
        regime = "risk_off"

    return ForecastCheck(
        "Cross-Regime Pressure",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "window": window,
            "def_syms": sorted(def_syms),
            "cyc_syms": sorted(cyc_syms),
            "def_ret_window": def_ret,
            "cyc_ret_window": cyc_ret,
            "spread_cyc_minus_def": spread,
            "flat_band_threshold": flat_band,
            "regime": regime,
            "is_defensive": is_def,
        },
        source_quality="proxy",
        fallback_used=False,
    )


def e6_driver_alignment(
    *,
    horizon_days: int,
    rs_slope_10: Optional[float],
    spy_outlook_score: int,
    vix_outlook_score: int,
) -> ForecastCheck:
    H = max(1, int(horizon_days or 1))
    h_scale = float(H**0.5)
    meaning = "Are the main drivers aligned for this symbol into H (market regime + local RS trend)?"

    rs = float(rs_slope_10) if isinstance(rs_slope_10, (int, float)) else 0.0

    macro_bias = 0
    if int(spy_outlook_score) >= 2:
        macro_bias += 1
    elif int(spy_outlook_score) <= 0:
        macro_bias -= 1

    if int(vix_outlook_score) >= 2:
        macro_bias += 1
    elif int(vix_outlook_score) <= 0:
        macro_bias -= 1

    strong_rs = 0.00030 * h_scale
    ok_rs = 0.00006 * h_scale
    mild_neg = -0.00010 * h_scale
    deep_neg = -0.00055 * h_scale

    if macro_bias >= 2:
        if rs >= ok_rs:
            sc = 2
        elif rs >= deep_neg:
            sc = 1 if H <= 2 else 2
        else:
            sc = 0
    elif macro_bias == 1:
        if rs >= strong_rs:
            sc = 2
        elif rs >= mild_neg:
            sc = 1
        else:
            sc = 0
    elif macro_bias == 0:
        if rs >= strong_rs:
            sc = 2 if H <= 2 else 1
        elif rs >= 0.0:
            sc = 1
        else:
            sc = 1 if (H <= 2 and rs >= mild_neg) else 0
    elif macro_bias == -1:
        if rs >= strong_rs and H <= 2:
            sc = 1
        elif rs >= ok_rs and H <= 1:
            sc = 1
        else:
            sc = 0
    else:
        if rs >= strong_rs and H <= 1:
            sc = 1
        else:
            sc = 0

    return ForecastCheck(
        "Driver Alignment",
        meaning,
        sc,
        {
            "H": H,
            "horizon_scale": h_scale,
            "rs_slope_10": rs_slope_10,
            "spy_outlook_score": spy_outlook_score,
            "vix_outlook_score": vix_outlook_score,
            "macro_bias": macro_bias,
            "strong_rs_threshold": strong_rs,
            "ok_rs_threshold": ok_rs,
            "mild_negative_threshold": mild_neg,
            "deep_negative_threshold": deep_neg,
        },
        source_quality="proxy",
        fallback_used=False,
    )
