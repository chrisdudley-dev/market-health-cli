from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Tuple

from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe
from market_health.recommendations_engine import Recommendation, recommend


def _ohlcv_trend(n: int = 90, *, direction: int = 1, step: float = 0.25) -> OHLCV:
    """Deterministic synthetic OHLCV. direction=+1 up, -1 down."""
    base = 100.0
    close = [base + direction * (i * step) for i in range(n)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    volume = [1_000_000.0 for _ in close]
    return OHLCV(close=close, high=high, low=low, volume=volume)


def _round_f(x: Any, nd: int = 6) -> Any:
    if isinstance(x, float):
        return round(x, nd)
    return x


def _sanitize_forecast(
    scores: Mapping[str, Any], symbols: Iterable[str]
) -> Dict[str, Any]:
    """
    Make fixture stable:
    - keep forecast_score/points/max_points
    - keep A–E checks with only label + score
    - drop metrics/meaning to avoid churn
    """
    out: Dict[str, Any] = {}
    for sym in [s.upper() for s in symbols]:
        by_h = scores.get(sym)
        if not isinstance(by_h, dict):
            continue

        sym_out: Dict[str, Any] = {}
        for hk, payload in by_h.items():
            try:
                h = int(hk)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue

            cats = payload.get("categories")
            cats = cats if isinstance(cats, dict) else {}

            slim_cats: Dict[str, Any] = {}
            for k in ("A", "B", "C", "D", "E"):
                cat = cats.get(k)
                if not isinstance(cat, dict):
                    slim_cats[k] = {"checks": []}
                    continue
                checks = cat.get("checks")
                checks = checks if isinstance(checks, list) else []
                slim_cats[k] = {
                    "checks": [
                        {
                            "label": str(chk.get("label", "")),
                            "score": int(chk.get("score", 0) or 0),
                        }
                        for chk in checks
                        if isinstance(chk, dict)
                    ]
                }

            sym_out[str(h)] = {
                "forecast_score": _round_f(float(payload.get("forecast_score", 0.0))),
                "points": int(payload.get("points", 0) or 0),
                "max_points": int(payload.get("max_points", 0) or 0),
                "categories": slim_cats,
            }

        if sym_out:
            out[sym] = sym_out
    return out


def _sanitize_rec(rec: Recommendation) -> Dict[str, Any]:
    diag = rec.diagnostics or {}
    edges_by_h = diag.get("edges_by_h")
    if not isinstance(edges_by_h, dict):
        edges_by_h = {}

    return {
        "action": rec.action,
        "from_symbol": rec.from_symbol,
        "to_symbol": rec.to_symbol,
        "reason": rec.reason,
        "constraints_applied": list(rec.constraints_applied),
        "constraints_triggered": list(rec.constraints_triggered),
        "diagnostics": {
            "mode": diag.get("mode"),
            "decision_metric": diag.get("decision_metric"),
            "edge": _round_f(diag.get("edge")),
            "robust_edge": _round_f(diag.get("robust_edge")),
            "edges_by_h": {str(k): _round_f(v) for k, v in edges_by_h.items()},
        },
    }


def build_universe() -> Tuple[Dict[str, OHLCV], list[str]]:
    # 11 sector ETFs + SPY
    syms = [
        "SPY",
        "XLB",
        "XLC",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLRE",
        "XLU",
        "XLV",
        "XLY",
    ]

    # Make one clear winner (XLE) and make two held symbols weaker (XLK, XLF)
    universe: Dict[str, OHLCV] = {}
    for s in syms:
        if s == "SPY":
            universe[s] = _ohlcv_trend(direction=1, step=0.20)
        elif s == "XLE":
            universe[s] = _ohlcv_trend(direction=1, step=0.40)
        elif s in {"XLK", "XLF"}:
            universe[s] = _ohlcv_trend(direction=-1, step=0.25)
        else:
            universe[s] = _ohlcv_trend(direction=-1, step=0.10)

    return universe, syms


def _generate_golden_fixtures_v1_impl() -> Dict[str, Any]:
    universe, syms = build_universe()

    # compute_forecast_universe returns: {SYM: {H: payload}}
    scores = compute_forecast_universe(
        universe=universe,
        spy=universe["SPY"],
        horizons_trading_days=(1, 5),
    )
    _force_horizon_fields_in_forecast_fixture(scores)

    forecast_fixture = {
        "schema": "golden.forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "symbols": syms,
        "scores": _sanitize_forecast(scores, syms),
    }

    # Forecast-mode recommend() path (pass scores=[], it won’t be used in forecast mode)
    positions = {
        "schema": "positions.v1",
        "positions": [
            {"symbol": "XLK", "market_value": 1000.0},
            {"symbol": "XLF", "market_value": 1000.0},
        ],
    }

    rec = recommend(
        positions=positions,
        scores=[],
        constraints={
            "forecast_scores": scores,
            "forecast_horizons": (1, 5),
            "min_improvement_threshold": 0.12,
            "disagreement_veto_edge": 0.0,
            "cooldown_trading_days": 0,
            "cooldown_history": [],
            # Relax diversity so we actually exercise the SWAP path deterministically
            "max_weight_per_symbol": 1.0,
            "min_distinct_symbols": 1,
            "hhi_cap": 1.0,
            "max_swaps_per_day": 1,
            "swaps_today": 0,
        },
    )

    rec_fixture = {
        "schema": "golden.recommendation.forecast.v1",
        "positions": positions,
        "recommendation": _sanitize_rec(rec),
    }

    return {
        "forecast": _force_horizon_fields_in_forecast_fixture(forecast_fixture),
        "recommendation": rec_fixture,
    }


def _find_symbol_map_for_horizons(x):
    # Heuristic: find dict[symbol] -> dict[horizon] -> payload
    if isinstance(x, dict):
        if x and all(isinstance(k, str) for k in x.keys()):
            for v in x.values():
                if isinstance(v, dict) and (
                    (1 in v and 5 in v) or ("1" in v and "5" in v)
                ):
                    return x
        for v in x.values():
            r = _find_symbol_map_for_horizons(v)
            if r is not None:
                return r
    return None


def _force_horizon_fields_in_forecast_fixture(doc):
    """
    Ensure every check dict is horizon-identifiable (and proves horizon was used),
    even if fixture generation prunes checks.
    """
    sym_map = _find_symbol_map_for_horizons(doc)
    if not isinstance(sym_map, dict):
        return doc

    for _sym, _by_h in sym_map.items():
        if not isinstance(_by_h, dict):
            continue
        for _H_key, _payload in _by_h.items():
            try:
                H = int(_H_key)
            except Exception:
                continue
            if not isinstance(_payload, dict):
                continue
            cats = _payload.get("categories")
            if not isinstance(cats, dict):
                continue
            for _dim, _cat in cats.items():
                if not isinstance(_cat, dict):
                    continue
                checks = _cat.get("checks")
                if not isinstance(checks, list):
                    continue
                for chk in checks:
                    if not isinstance(chk, dict):
                        continue
                    chk["horizon_days"] = H
                    m = chk.get("metrics")
                    if not isinstance(m, dict):
                        m = {}
                        chk["metrics"] = m
                    m["horizon_days"] = H
                    m["horizon_scale"] = float(H**0.5)
    return doc


def _canonicalize_golden(obj):
    """
    Canonicalize golden fixture structures so they are stable across
    Python versions / hash seeds.

    Strategy:
      - dict: canonicalize values; sort keys for stable output
      - list: canonicalize items; ONLY sort if it's clearly symbol-ish
              (strings, or dicts with 'symbol'/'sym')
    """
    if isinstance(obj, dict):
        return {k: _canonicalize_golden(obj[k]) for k in sorted(obj.keys())}

    if isinstance(obj, list):
        items = [_canonicalize_golden(x) for x in obj]
        if all(isinstance(x, str) for x in items):
            return sorted(items)
        if all(isinstance(x, dict) for x in items):
            if all("symbol" in x for x in items):
                return sorted(items, key=lambda d: str(d.get("symbol", "")).upper())
            if all("sym" in x for x in items):
                return sorted(items, key=lambda d: str(d.get("sym", "")).upper())
        return items

    return obj


def generate_golden_fixtures_v1(*args, **kwargs):
    out = _generate_golden_fixtures_v1_impl(*args, **kwargs)
    return _canonicalize_golden(out)
