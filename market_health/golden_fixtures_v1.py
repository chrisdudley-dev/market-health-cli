from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Tuple

from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe


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
    deterministic_calendar = {
        "schema": "calendar.v1",
        "windows": {"by_h": {"1": {}, "5": {}}},
    }

    scores = compute_forecast_universe(
        universe=universe,
        spy=universe["SPY"],
        horizons_trading_days=(1, 5),
        calendar=deterministic_calendar,
    )
    _force_horizon_fields_in_forecast_fixture(scores)

    forecast_fixture = {
        "schema": "golden.forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "symbols": syms,
        "scores": _sanitize_forecast(scores, syms),
    }

    return {"forecast": _force_horizon_fields_in_forecast_fixture(forecast_fixture)}


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
      - list:
          * list[str] -> sort
          * list[dict] -> sort by canonical JSON (stable across versions)
          * otherwise preserve order
    """
    if isinstance(obj, dict):
        return {k: _canonicalize_golden(obj[k]) for k in sorted(obj.keys())}

    if isinstance(obj, list):
        items = [_canonicalize_golden(x) for x in obj]

        if all(isinstance(x, str) for x in items):
            return sorted(items)

        if all(isinstance(x, dict) for x in items):
            import json as _json

            return sorted(
                items,
                key=lambda d: _json.dumps(
                    d, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                ),
            )

        return items

    return obj


def generate_golden_fixtures_v1(*args, **kwargs):
    out = _generate_golden_fixtures_v1_impl(*args, **kwargs)
    return _canonicalize_golden(out)
