"""market_health.forecast_recommendations

Forecast-driven recommendation path (Issue #113).

Pure/deterministic: no I/O. Export layer provides:
  - forecast_scores (forecast_scores.v1["scores"])
  - optional horizons list
  - thresholds / knobs
  - optional cooldown history (SwapEvent[])
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from market_health.forecast_policy import rank_candidates_by_robust_edge
from market_health.diversity_constraints import apply_swap, check_diversity
from market_health.cooldown_policy import SwapEvent, check_cooldown

# Import types/helpers from legacy engine (safe: imported lazily by recommend()).
from market_health.recommendations_engine import (
    Recommendation,
    extract_held_symbols,
    stable_tiebreak_key,
)


def _weights_from_positions(positions: Any) -> Dict[str, float]:
    """Convert positions.v1-like dict into symbol->weight map.

    Prefers market_value-like fields if present; otherwise equal-weight.
    """
    held = extract_held_symbols(positions)
    if not held:
        return {}

    if isinstance(positions, dict) and isinstance(positions.get("positions"), list):
        vals: Dict[str, float] = {}
        for p in positions["positions"]:
            if not isinstance(p, dict):
                continue
            sym = p.get("symbol") or p.get("ticker")
            if not isinstance(sym, str) or not sym.strip():
                continue
            sym_u = sym.strip().upper()
            mv = (
                p.get("market_value")
                or p.get("marketValue")
                or p.get("market_value_usd")
                or p.get("value")
            )
            if isinstance(mv, (int, float)) and mv > 0:
                vals[sym_u] = float(mv)
        if vals:
            total = sum(vals.values())
            if total > 0:
                return {k: v / total for k, v in vals.items()}

    n = max(1, len(held))
    return {s: 1.0 / n for s in held}


def _held_min_score(
    sym: str, scores: Dict[str, Any], horizons: Tuple[int, ...]
) -> float:
    by_h = scores.get(sym, {})
    vals: List[float] = []
    if isinstance(by_h, dict):
        for H in horizons:
            payload = by_h.get(H) or by_h.get(str(H))
            if isinstance(payload, dict) and isinstance(
                payload.get("forecast_score"), (int, float)
            ):
                vals.append(float(payload["forecast_score"]))
    return min(vals) if vals else float("inf")


def recommend_forecast_mode(
    *, positions: Any, constraints: Dict[str, Any]
) -> Recommendation:
    horizon = int(constraints.get("horizon_trading_days", 5) or 5)
    thr = float(constraints.get("min_improvement_threshold", 0.12))
    veto_edge = float(constraints.get("disagreement_veto_edge", 0.0))

    max_swaps = int(constraints.get("max_swaps_per_day", 1) or 1)
    swaps_today = int(constraints.get("swaps_today", 0) or 0)

    scores = constraints.get("forecast_scores") or {}
    if not isinstance(scores, dict) or not scores:
        return Recommendation(
            action="NOOP",
            reason="Forecast mode enabled but forecast_scores missing/unreadable.",
            horizon_trading_days=horizon,
            constraints_applied=("forecast_mode",),
            diagnostics={"mode": "forecast", "forecast_mode_status": "missing_scores"},
        )

    horizons_raw = constraints.get("forecast_horizons") or (1, 5)
    horizons = (
        tuple(int(h) for h in horizons_raw)
        if isinstance(horizons_raw, (list, tuple))
        else (1, 5)
    )

    applied = (
        "forecast_mode",
        "robust_edge=min(edge(H))",
        "disagreement_veto_edge",
        "diversity_constraints",
        "cooldown",
        "max_swaps_per_day",
        "min_improvement_threshold",
    )

    held = [s.upper() for s in extract_held_symbols(positions)]
    if not held:
        return Recommendation(
            action="NOOP",
            reason="No held symbols found; nothing to do.",
            horizon_trading_days=horizon,
            constraints_applied=applied,
            diagnostics={
                "mode": "forecast",
                "threshold": thr,
                "forecast_horizons": horizons,
            },
        )

    held_present = [h for h in held if h in scores]
    if not held_present:
        return Recommendation(
            action="NOOP",
            reason="Held symbols not found in forecast-scored universe; cannot compare.",
            horizon_trading_days=horizon,
            constraints_applied=applied,
            diagnostics={
                "mode": "forecast",
                "held": held,
                "forecast_horizons": horizons,
            },
        )

    weakest = min(
        held_present,
        key=lambda s: (_held_min_score(s, scores, horizons), stable_tiebreak_key(s)),
    )

    candidates = [s for s in scores.keys() if s not in set(held_present)]
    if not candidates:
        return Recommendation(
            action="NOOP",
            reason="No candidates available outside held set.",
            horizon_trading_days=horizon,
            constraints_applied=applied,
            diagnostics={
                "mode": "forecast",
                "held": held_present,
                "forecast_horizons": horizons,
            },
        )

    ranked = rank_candidates_by_robust_edge(
        from_symbol=weakest,
        candidate_symbols=candidates,
        scores=scores,
        horizons_trading_days=horizons,
        disagreement_veto_edge=veto_edge,
    )
    best = ranked[0]

    diagnostics = {
        "mode": "forecast",
        "threshold": thr,
        "horizon_trading_days": horizon,
        "forecast_horizons": horizons,
        "weakest_held": weakest,
        "best_candidate": best.to_symbol,
        "robust_edge": best.robust_edge,
        "decision_metric": "robust_edge",
        "edge": best.robust_edge,
        "avg_edge": best.avg_edge,
        "edges_by_h": {str(h): best.edges_by_h.get(h) for h in horizons},
        # keep legacy UI key until #115 updates display text
        "delta_utility": best.robust_edge,
        "disagreement_veto_edge": veto_edge,
        "vetoed": best.vetoed,
        "veto_reason": best.veto_reason,
    }

    if best.vetoed:
        return Recommendation(
            action="NOOP",
            reason=f"Forecast veto: {best.veto_reason}",
            horizon_trading_days=horizon,
            constraints_applied=applied,
            constraints_triggered=("disagreement_veto_edge",),
            diagnostics=diagnostics,
        )

    if not (best.robust_edge >= thr and best.to_symbol != weakest):
        return Recommendation(
            action="NOOP",
            reason=f"No candidate clears robust threshold (best={best.robust_edge:.3f} < {thr:.3f}); hold.",
            horizon_trading_days=horizon,
            constraints_applied=applied,
            constraints_triggered=("min_improvement_threshold",),
            diagnostics=diagnostics,
        )

    triggered: List[str] = []

    if swaps_today >= max_swaps:
        triggered.append("max_swaps_per_day")

    w = _weights_from_positions(positions)
    w2 = apply_swap(w, weakest, best.to_symbol)
    div = check_diversity(
        w2,
        max_weight_per_symbol=float(constraints.get("max_weight_per_symbol", 0.25)),
        min_distinct_symbols=int(constraints.get("min_distinct_symbols", 4)),
        hhi_cap=float(constraints.get("hhi_cap", 0.20)),
    )
    diagnostics.update(
        {
            "diversity_ok": div.ok,
            "diversity_reasons": list(div.reasons),
            "diversity": {
                "max_weight": div.max_weight,
                "distinct": div.distinct,
                "hhi": div.hhi,
            },
        }
    )
    if not div.ok:
        triggered.append("diversity_constraints")

    cooldown_days = int(constraints.get("cooldown_trading_days", 0) or 0)
    history = constraints.get("cooldown_history") or []
    if cooldown_days > 0 and isinstance(history, list):
        hist = [h for h in history if isinstance(h, SwapEvent)]
        cd = check_cooldown(
            proposed_from=weakest,
            proposed_to=best.to_symbol,
            history=hist,
            cooldown_trading_days=cooldown_days,
        )
        diagnostics.update(
            {"cooldown_vetoed": cd.vetoed, "cooldown_reason": cd.veto_reason}
        )
        if cd.vetoed:
            triggered.append("cooldown")

    if triggered:
        return Recommendation(
            action="NOOP",
            reason="Forecast swap blocked by constraints: " + ", ".join(triggered),
            horizon_trading_days=horizon,
            constraints_applied=applied,
            constraints_triggered=tuple(triggered),
            diagnostics=diagnostics,
        )

    return Recommendation(
        action="SWAP",
        reason=f"Forecast robust edge {best.robust_edge:.3f} clears threshold {thr:.3f}.",
        from_symbol=weakest,
        to_symbol=best.to_symbol,
        horizon_trading_days=horizon,
        target_trade_date=None,
        constraints_applied=applied,
        constraints_triggered=(),
        diagnostics=diagnostics,
    )
