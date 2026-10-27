"""Preserved numerical Blend helpers; decisions live in market_health.policy."""

from __future__ import annotations


from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


Action = str


@dataclass(frozen=True)
class Recommendation:
    action: Action
    reason: str

    # Historical artifact fields
    from_symbol: Optional[str] = None
    to_symbol: Optional[str] = None

    # Scheduling (filled later; M9 adds trading-day semantics)
    horizon_trading_days: int = 0
    target_trade_date: Optional[str] = None  # YYYY-MM-DD or None

    # Explainability / auditing
    constraints_applied: Tuple[str, ...] = ()
    constraints_triggered: Tuple[str, ...] = ()
    diagnostics: Dict[str, Any] = None  # type: ignore[assignment]


def stable_tiebreak_key(symbol: str) -> Tuple[str]:
    return (symbol.upper(),)


def extract_held_symbols(positions: Any) -> List[str]:
    if positions is None:
        return []

    if isinstance(positions, (list, tuple, set)):
        syms = [str(x).strip().upper() for x in positions if str(x).strip()]
        return sorted(set(syms), key=stable_tiebreak_key)

    if isinstance(positions, dict):
        plist = positions.get("positions")
        if isinstance(plist, list):
            out: List[str] = []
            for p in plist:
                if not isinstance(p, dict):
                    continue
                sym = p.get("symbol") or p.get("ticker")
                if isinstance(sym, str) and sym.strip():
                    out.append(sym.strip().upper())
            return sorted(set(out), key=stable_tiebreak_key)

    return []


def score_row_points(row: Dict[str, Any]) -> Tuple[int, int]:
    cats = row.get("categories", {})
    if not isinstance(cats, dict):
        return (0, 0)

    points = 0
    checks_n = 0
    # Canonical core utility is A-E only (ignore legacy F or any extra categories)
    for key in ("A", "B", "C", "D", "E"):
        cat = cats.get(key)
        if not isinstance(cat, dict):
            continue
        checks = cat.get("checks", [])
        if not isinstance(checks, list):
            continue
        for chk in checks:
            if not isinstance(chk, dict):
                continue
            sc = chk.get("score")
            if isinstance(sc, int):
                points += sc
                checks_n += 1
    return (points, 2 * checks_n)


def _normalize_utility_weights(raw: Any) -> Dict[str, float]:
    base = {"c": 0.50, "h1": 0.25, "h5": 0.25}
    if not isinstance(raw, dict):
        return dict(base)

    vals: Dict[str, float] = {}
    for key in ("c", "h1", "h5"):
        v = raw.get(key)
        if isinstance(v, (int, float)) and float(v) >= 0:
            vals[key] = float(v)
        else:
            vals[key] = base[key]

    total = sum(vals.values())
    if total <= 0:
        return dict(base)
    return {k: (v / total) for k, v in vals.items()}


def _forecast_payload_for(
    forecast_scores: Any, sym: str, horizon_trading_days: int
) -> Optional[Dict[str, Any]]:
    if not isinstance(forecast_scores, dict):
        return None
    by_h = forecast_scores.get(sym)
    if not isinstance(by_h, dict):
        return None
    raw = by_h.get(str(horizon_trading_days), by_h.get(horizon_trading_days))
    return raw if isinstance(raw, dict) else None


def _forecast_utility(payload: Any, *, current_utility: float) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    score = payload.get("forecast_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    score = float(score)
    if abs(score) > 1.000001:
        score = score / 100.0
    return max(0.0, min(1.0, score))


def _blend_utility_diagnostic(
    *,
    parts: Dict[str, Any],
    weights: Dict[str, float],
    blended: float,
) -> Dict[str, Any]:
    order = ("c", "h1", "h5")
    present = {k: parts.get(k) for k in order if isinstance(parts.get(k), (int, float))}
    denominator = sum(float(weights[k]) for k in present)

    components: Dict[str, Dict[str, Any]] = {}
    for key in order:
        value = parts.get(key)
        is_present = isinstance(value, (int, float))
        base_weight = float(weights.get(key, 0.0))
        effective_weight = (
            base_weight / denominator if is_present and denominator > 0 else 0.0
        )
        numeric_value = float(value) if is_present else None
        contribution = (
            effective_weight * numeric_value if numeric_value is not None else 0.0
        )
        components[key] = {
            "present": is_present,
            "value": numeric_value,
            "base_weight": base_weight,
            "effective_weight": effective_weight,
            "contribution": contribution,
        }

    return {
        "formula": "blend=sum(effective_weight(component)*utility(component)) over present c,h1,h5 components",
        "component_order": list(order),
        "raw_weights": {k: float(weights.get(k, 0.0)) for k in order},
        "present_components": [k for k in order if k in present],
        "denominator": denominator,
        "components": components,
        "blended_utility": float(blended),
    }


def blended_utility_from_scores(
    rows: Iterable[Dict[str, Any]],
    *,
    forecast_scores: Any = None,
    utility_weights: Any = None,
    forecast_horizons: Any = (1, 5),
) -> Dict[str, Dict[str, Any]]:
    out = utility_from_scores(rows)
    weights = _normalize_utility_weights(utility_weights)

    horizons: List[int] = []
    if isinstance(forecast_horizons, (list, tuple)):
        for h in forecast_horizons:
            try:
                horizons.append(int(h))
            except Exception:
                continue
    if len(horizons) < 2:
        horizons = [1, 5]
    h1, h5 = horizons[0], horizons[1]

    for sym, meta in out.items():
        c_util = float(meta.get("utility", 0.0))
        h1_util = _forecast_utility(
            _forecast_payload_for(forecast_scores, sym, h1), current_utility=c_util
        )
        h5_util = _forecast_utility(
            _forecast_payload_for(forecast_scores, sym, h5), current_utility=c_util
        )

        parts = {"c": c_util, "h1": h1_util, "h5": h5_util}
        present = {k: v for k, v in parts.items() if isinstance(v, (int, float))}
        denom = sum(weights[k] for k in present.keys())
        blended = (
            sum(weights[k] * float(v) for k, v in present.items()) / denom
            if denom > 0
            else c_util
        )

        meta.update(
            {
                "utility": blended,
                "current_utility": c_util,
                "h1_utility": h1_util,
                "h5_utility": h5_util,
                "utility_weights": dict(weights),
                "utility_blend_diagnostic": _blend_utility_diagnostic(
                    parts=parts,
                    weights=weights,
                    blended=blended,
                ),
            }
        )
    return out


def utility_from_scores(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = row.get("symbol")
        if not isinstance(sym, str) or not sym.strip():
            continue
        sym_u = sym.strip().upper()
        pts, mx = score_row_points(row)
        util = (pts / mx) if mx > 0 else 0.0
        out[sym_u] = {"utility": util, "points": pts, "max_points": mx}
    return out


def recommend(**kwargs):
    raise RuntimeError(
        "Legacy recommendations are retired. Use market_health.policy.evaluate and local portfolio ownership."
    )
