"""
forecast_policy.py

Multi-horizon policy primitives for forecast-driven rotation.

Issue #110 scope:
- robust_edge = min(edge(H)) across configured horizons
- disagreement veto if any edge(H) < disagreement_veto_edge
- deterministic, pure, no I/O
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

Number = Union[int, float]


@dataclass(frozen=True)
class MultiHorizonEdge:
    from_symbol: str
    to_symbol: str
    horizons: Tuple[int, ...]
    edges_by_h: Dict[int, float]
    robust_edge: float
    avg_edge: float
    vetoed: bool
    veto_reason: str


def _get_payload(scores: Mapping[str, Any], symbol: str) -> Optional[Mapping[str, Any]]:
    s = symbol.upper()
    v = scores.get(s)
    if isinstance(v, dict):
        return v
    v = scores.get(symbol)
    return v if isinstance(v, dict) else None


def _get_forecast_score(scores: Mapping[str, Any], symbol: str, H: int) -> Optional[float]:
    by_h = _get_payload(scores, symbol)
    if by_h is None:
        return None

    payload = by_h.get(H)
    if payload is None:
        payload = by_h.get(str(H))

    if not isinstance(payload, dict):
        return None

    fs = payload.get("forecast_score")
    if isinstance(fs, (int, float)):
        return float(fs)
    return None


def compute_multi_horizon_edge(
    *,
    from_symbol: str,
    to_symbol: str,
    scores: Mapping[str, Any],
    horizons_trading_days: Iterable[int] = (1, 5),
    disagreement_veto_edge: float = 0.0,
) -> MultiHorizonEdge:
    hs = tuple(int(h) for h in horizons_trading_days)
    if not hs:
        raise ValueError("horizons_trading_days must be non-empty")

    edges: Dict[int, float] = {}
    missing: list[int] = []

    for h in hs:
        f_from = _get_forecast_score(scores, from_symbol, h)
        f_to = _get_forecast_score(scores, to_symbol, h)
        if f_from is None or f_to is None:
            missing.append(h)
            continue
        edges[h] = f_to - f_from

    if missing:
        return MultiHorizonEdge(
            from_symbol=from_symbol.upper(),
            to_symbol=to_symbol.upper(),
            horizons=hs,
            edges_by_h=edges,
            robust_edge=float("-inf"),
            avg_edge=float("-inf"),
            vetoed=True,
            veto_reason=f"missing_horizons:{','.join(str(h) for h in missing)}",
        )

    robust = min(edges.values()) if edges else float("-inf")
    avg = sum(edges.values()) / len(edges) if edges else float("-inf")

    bad = [h for h, e in edges.items() if e < disagreement_veto_edge]
    vetoed = len(bad) > 0
    reason = ""
    if vetoed:
        reason = f"disagreement_veto:edge({','.join(str(h) for h in sorted(bad))})<{disagreement_veto_edge:g}"

    return MultiHorizonEdge(
        from_symbol=from_symbol.upper(),
        to_symbol=to_symbol.upper(),
        horizons=hs,
        edges_by_h={int(k): float(v) for k, v in edges.items()},
        robust_edge=float(robust),
        avg_edge=float(avg),
        vetoed=vetoed,
        veto_reason=reason,
    )


def rank_candidates_by_robust_edge(
    *,
    from_symbol: str,
    candidate_symbols: Iterable[str],
    scores: Mapping[str, Any],
    horizons_trading_days: Iterable[int] = (1, 5),
    disagreement_veto_edge: float = 0.0,
) -> list[MultiHorizonEdge]:
    items: list[MultiHorizonEdge] = []
    for to_sym in candidate_symbols:
        mh = compute_multi_horizon_edge(
            from_symbol=from_symbol,
            to_symbol=to_sym,
            scores=scores,
            horizons_trading_days=horizons_trading_days,
            disagreement_veto_edge=disagreement_veto_edge,
        )
        items.append(mh)

    items.sort(
        key=lambda x: (
            1 if x.vetoed else 0,
            -x.robust_edge,
            -x.avg_edge,
            x.to_symbol,
        )
    )
    return items
