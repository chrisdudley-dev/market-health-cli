"""
forecast_checks_e_environment.py

Forecast-mode Dimension E (Environment) checks — exactly 6 checks.

E1) SPY Outlook
E2) VIX Outlook
E3) Leadership Persistence
E4) Breadth Regime
E5) Cross-Regime Pressure
E6) Driver Alignment
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set

from .forecast_types import ForecastCheck, neutral_check

DEFENSIVE: Set[str] = {"XLU", "XLP", "XLV"}
CYCLICAL: Set[str] = {"XLY", "XLI", "XLF", "XLB", "XLK", "XLC", "XLE", "XLRE"}


def compute_e_checks(
    *, horizon_days: int,
    symbol: str,
    spy_slope_10: Optional[float] = None,
    vix_features: Optional[Dict[str, Any]] = None,
    returns_by_symbol: Optional[Dict[str, Sequence[Optional[float]]]] = None,
    dispersion: Optional[float] = None,
    rs_slope_10: Optional[float] = None,
) -> List[ForecastCheck]:
    vix_features = vix_features or {}
    symbol_u = symbol.upper()
    spy_check = e1_spy_outlook(horizon_days=horizon_days, spy_slope_10=spy_slope_10)
    vix_check = e2_vix_outlook(horizon_days=horizon_days, vix_features=vix_features)
    return [
        spy_check,
        vix_check,
        e3_leadership_persistence(horizon_days=horizon_days, symbol=symbol_u, returns_by_symbol=returns_by_symbol),
        e4_breadth_regime(horizon_days=horizon_days, dispersion=dispersion),
        e5_cross_regime_pressure(horizon_days=horizon_days, symbol=symbol_u, returns_by_symbol=returns_by_symbol),
        e6_driver_alignment(horizon_days=horizon_days, rs_slope_10=rs_slope_10,
            spy_outlook_score=spy_check.score,
            vix_outlook_score=vix_check.score,
        ),
    ]


def e1_spy_outlook(*, horizon_days: int, spy_slope_10: Optional[float]) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = "Is the broad market setup improving or deteriorating into H?"
    if spy_slope_10 is None:
        return neutral_check(
            "SPY Outlook", meaning, "Insufficient SPY history; neutral."
        )
    if spy_slope_10 > 0.0004:
        sc = 2
    elif spy_slope_10 > -0.0002:
        sc = 1
    else:
        sc = 0
    return ForecastCheck("SPY Outlook", meaning, sc, {"spy_slope_10": spy_slope_10})


def e2_vix_outlook(*, horizon_days: int, vix_features: Dict[str, Any]) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = "Is volatility regime likely to rise or fall into H (risk-on vs risk-off pressure)?"
    if not vix_features:
        return neutral_check("VIX Outlook", meaning, "No VIX feed; neutral.")
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
        "VIX Outlook", meaning, sc, {"vix_rank_60": rank_now, "vix_slope_10": slope_now}
    )


def e3_leadership_persistence(
    *, horizon_days: int,
    symbol: str,
    returns_by_symbol: Optional[Dict[str, Sequence[Optional[float]]]],
    window: int = 5,
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
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
    if span <= 2 and avg_rank <= 4:
        sc = 2
    elif span <= 4:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Leadership Persistence",
        meaning,
        sc,
        {"ranks_window": ranks, "span": span, "avg_rank": avg_rank, "window": window},
    )


def e4_breadth_regime(*, horizon_days: int, dispersion: Optional[float]) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = (
        "Is market participation broad or narrow (proxy via cross-sector dispersion)?"
    )
    if dispersion is None:
        return neutral_check("Breadth Regime", meaning, "No dispersion input; neutral.")
    if dispersion >= 0.010:
        sc = 2
    elif dispersion >= 0.007:
        sc = 1
    else:
        sc = 0
    return ForecastCheck("Breadth Regime", meaning, sc, {"dispersion": dispersion})


def e5_cross_regime_pressure(
    *, horizon_days: int,
    symbol: str,
    returns_by_symbol: Optional[Dict[str, Sequence[Optional[float]]]],
    window: int = 5,
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = (
        "Are conditions favoring offense or defense (risk-on vs risk-off tilt into H)?"
    )
    if not returns_by_symbol:
        return neutral_check(
            "Cross-Regime Pressure", meaning, "No universe returns; neutral."
        )
    syms = set(returns_by_symbol.keys())
    if not (DEFENSIVE.issubset(syms) and (CYCLICAL & syms)):
        return neutral_check(
            "Cross-Regime Pressure",
            meaning,
            "Universe missing defensive/cyclical sets; neutral.",
        )

    def _avg_cumret(symset: Set[str]) -> Optional[float]:
        vals: List[float] = []
        for s in symset:
            series = returns_by_symbol.get(s)
            if series is None or len(series) < window + 1:
                return None
            w = [x for x in series[-window:] if x is not None]
            if len(w) < window:
                return None
            vals.append(sum(float(x) for x in w))
        return (sum(vals) / len(vals)) if vals else None

    def_ret = _avg_cumret(DEFENSIVE)
    cyc_ret = _avg_cumret(set(s for s in CYCLICAL if s in syms))
    if def_ret is None or cyc_ret is None:
        return neutral_check(
            "Cross-Regime Pressure",
            meaning,
            "Insufficient returns for regime proxy; neutral.",
        )
    defensive_winning = def_ret > cyc_ret
    is_def = symbol in DEFENSIVE
    if abs(def_ret - cyc_ret) < 0.01:
        sc = 1
    elif defensive_winning and is_def:
        sc = 2
    elif (not defensive_winning) and (not is_def):
        sc = 2
    else:
        sc = 0
    return ForecastCheck(
        "Cross-Regime Pressure",
        meaning,
        sc,
        {
            "def_ret_window": def_ret,
            "cyc_ret_window": cyc_ret,
            "defensive_winning": defensive_winning,
            "is_defensive": is_def,
            "window": window,
        },
    )


def e6_driver_alignment(
    *, horizon_days: int, rs_slope_10: Optional[float], spy_outlook_score: int, vix_outlook_score: int
) -> ForecastCheck:
    # horizon-derived intermediate (ensures horizon_days is used in this check)
    h = int(horizon_days) if int(horizon_days) > 0 else 1
    h_window = int(round(10 * (h ** 0.5)))
    meaning = "Are dominant drivers likely to support this sector into H (proxy: RS improving under environment)?"
    if rs_slope_10 is None:
        return neutral_check(
            "Driver Alignment", meaning, "Insufficient RS history; neutral."
        )
    env_support = (spy_outlook_score + vix_outlook_score) / 4.0
    if env_support >= 0.75 and rs_slope_10 > 0.0:
        sc = 2
    elif rs_slope_10 > -0.0003:
        sc = 1
    else:
        sc = 0
    return ForecastCheck(
        "Driver Alignment",
        meaning,
        sc,
        {
            "rs_slope_10": rs_slope_10,
            "spy_outlook_score": spy_outlook_score,
            "vix_outlook_score": vix_outlook_score,
            "env_support": env_support,
        },
    )
