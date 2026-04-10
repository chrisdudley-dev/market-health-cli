"""market_health.forecast_recommendations

Forecast-driven recommendation path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from market_health.forecast_policy import rank_candidates_by_robust_edge
from market_health.diversity_constraints import apply_swap, check_diversity
from market_health.cooldown_policy import SwapEvent, check_cooldown
from market_health.recommendations_engine import (
    Recommendation,
    blended_utility_from_scores,
    extract_held_symbols,
    stable_tiebreak_key,
)


def _weights_from_positions(positions: Any) -> Dict[str, float]:
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


def _held_min_score(sym: str, scores: Dict[str, Any], horizons: Tuple[int, ...]) -> float:
    by_h = scores.get(sym, {})
    vals: List[float] = []
    if isinstance(by_h, dict):
        for H in horizons:
            payload = by_h.get(H) or by_h.get(str(H))
            if isinstance(payload, dict) and isinstance(payload.get("forecast_score"), (int, float)):
                vals.append(float(payload["forecast_score"]))
    return min(vals) if vals else float("inf")


def _component_snapshot(sym: str, blended_util: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    meta = blended_util.get(sym) if isinstance(blended_util, dict) else None
    if not isinstance(meta, dict):
        return {}
    cur = meta.get("current_utility")
    return {
        "c": cur,
        "current": cur,
        "h1": meta.get("h1_utility"),
        "h5": meta.get("h5_utility"),
        "blend": meta.get("utility"),
        "blended": meta.get("utility"),
    }


def _build_candidate_rows(
    *,
    ranked_pairs: List[Tuple[Any, Any, float, float]],
    blended_util: Dict[str, Dict[str, Any]],
    held_present: List[str],
    horizons: Tuple[int, ...],
    threshold: float,
) -> Tuple[List[Dict[str, Any]], float]:
    held_blends = [
        float(blended_util[s].get("utility"))
        for s in held_present
        if isinstance(blended_util.get(s), dict)
        and isinstance(blended_util[s].get("utility"), (int, float))
    ]
    weakest_held_blended = min(held_blends) if held_blends else 0.0

    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for _, pair, from_weight, weighted_robust_edge in ranked_pairs:
        sym = str(pair.to_symbol).strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)

        meta = blended_util.get(sym) if isinstance(blended_util, dict) else None
        meta = meta if isinstance(meta, dict) else {}

        blended = meta.get("utility")
        current = meta.get("current_utility")
        h1 = meta.get("h1_utility")
        h5 = meta.get("h5_utility")

        delta_blended = (
            round(float(blended) - float(weakest_held_blended), 2)
            if isinstance(blended, (int, float))
            else None
        )

        decision_metric = "portfolio_weighted_robust_edge"
        decision_value = float(weighted_robust_edge)

        status = "BLOCKED"
        if (
            not bool(pair.vetoed)
            and isinstance(decision_value, (int, float))
            and float(decision_value) >= float(threshold)
        ):
            status = "READY"

        rows.append(
            {
                "sym": sym,
                "symbol": sym,
                "candidate": sym,
                "to_symbol": sym,
                "from_symbol": pair.from_symbol,
                "decision_metric": decision_metric,
                "decision_value": decision_value,
                "robust_edge": float(pair.robust_edge),
                "weighted_robust_edge": float(weighted_robust_edge),
                "from_weight": from_weight,
                "blend": blended,
                "blended": blended,
                "c": current,
                "current": current,
                "h1": h1,
                "h5": h5,
                "delta_blended": delta_blended,
                "threshold": float(threshold),
                "status": status,
                "vetoed": bool(pair.vetoed),
                "veto_reason": pair.veto_reason,
                "robust_edge": pair.robust_edge,
                "weighted_robust_edge": weighted_robust_edge,
                "avg_edge": pair.avg_edge,
                "edges_by_h": {str(h): pair.edges_by_h.get(h) for h in horizons},
            }
        )

    return rows, weakest_held_blended


def recommend_forecast_mode(
    *, positions: Any, score_rows: Any = None, constraints: Dict[str, Any]
) -> Recommendation:
    horizon = int(constraints.get("horizon_trading_days", 5) or 5)

    calibration_doc = constraints.get("calibration") or {}
    if not isinstance(calibration_doc, dict):
        calibration_doc = {}

    calibration_doc_thresholds = calibration_doc.get("thresholds") or {}
    if not isinstance(calibration_doc_thresholds, dict):
        calibration_doc_thresholds = {}

    calibration_thresholds = constraints.get("calibration_thresholds") or {}
    if not isinstance(calibration_thresholds, dict):
        calibration_thresholds = {}

    effective_thresholds = dict(calibration_doc_thresholds)
    effective_thresholds.update(calibration_thresholds)

    thr = float(
        effective_thresholds.get(
            "min_improvement_threshold",
            constraints.get("min_improvement_threshold", 0.12),
        )
    )
    veto_edge = float(
        effective_thresholds.get(
            "disagreement_veto_edge",
            constraints.get("disagreement_veto_edge", 0.0),
        )
    )

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

    blended_util = blended_utility_from_scores(
        score_rows if isinstance(score_rows, list) else [],
        forecast_scores=scores,
        utility_weights=constraints.get("utility_weights"),
        forecast_horizons=horizons,
    )
    utility_weights = None
    if isinstance(blended_util, dict) and blended_util:
        meta0 = next(iter(blended_util.values()))
        if isinstance(meta0, dict):
            utility_weights = meta0.get("utility_weights")

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

    w = _weights_from_positions(positions)
    default_weight = 1.0 / max(1, len(held_present))

    ranked_pairs = []
    for from_sym in held_present:
        ranked = rank_candidates_by_robust_edge(
            from_symbol=from_sym,
            candidate_symbols=candidates,
            scores=scores,
            horizons_trading_days=horizons,
            disagreement_veto_edge=veto_edge,
        )
        if not ranked:
            continue

        from_weight = float(w.get(from_sym, default_weight))
        for pair in ranked:
            weighted_robust_edge = from_weight * pair.robust_edge
            key = (
                1 if pair.vetoed else 0,
                -weighted_robust_edge,
                -pair.robust_edge,
                -pair.avg_edge,
                pair.from_symbol,
                pair.to_symbol,
            )
            ranked_pairs.append((key, pair, from_weight, weighted_robust_edge))

    if not ranked_pairs:
        return Recommendation(
            action="NOOP",
            reason="No forecast pair candidates could be ranked.",
            horizon_trading_days=horizon,
            constraints_applied=applied,
            diagnostics={
                "mode": "forecast",
                "held": held_present,
                "forecast_horizons": horizons,
            },
        )

    ranked_pairs.sort(key=lambda item: item[0])

    candidate_rows, weakest_held_blended = _build_candidate_rows(
        ranked_pairs=ranked_pairs,
        blended_util=blended_util,
        held_present=held_present,
        horizons=horizons,
        threshold=thr,
    )

    held_components: Dict[str, Dict[str, Any]] = {}
    for sym in held_present:
        snap = _component_snapshot(sym, blended_util)
        if snap:
            held_components[sym] = snap

    candidate_components: Dict[str, Dict[str, Any]] = {}
    for row in candidate_rows:
        sym = str(row.get("sym") or "").strip().upper()
        if not sym:
            continue
        snap = _component_snapshot(sym, blended_util)
        if snap:
            candidate_components[sym] = snap

    _, best, from_weight, weighted_robust_edge = ranked_pairs[0]
    selected_from = best.from_symbol
    decision_metric = (
        "portfolio_weighted_robust_edge" if len(held_present) > 1 else "robust_edge"
    )

    pair_diagnostics = [
        {
            "from_symbol": pair.from_symbol,
            "to_symbol": pair.to_symbol,
            "from_weight": pair_weight,
            "weighted_robust_edge": pair_weighted_edge,
            "robust_edge": pair.robust_edge,
            "avg_edge": pair.avg_edge,
            "vetoed": pair.vetoed,
            "veto_reason": pair.veto_reason,
            "edges_by_h": {str(h): pair.edges_by_h.get(h) for h in horizons},
        }
        for _, pair, pair_weight, pair_weighted_edge in ranked_pairs
    ]

    diagnostics = {
        "mode": "forecast",
        "threshold": thr,
        "horizon_trading_days": horizon,
        "forecast_horizons": horizons,
        "weakest_held": weakest,
        "selected_from_symbol": selected_from,
        "best_candidate": best.to_symbol,
        "robust_edge": best.robust_edge,
        "weighted_robust_edge": weighted_robust_edge,
        "selected_weight": from_weight,
        "decision_metric": decision_metric,
        "edge": best.robust_edge,
        "avg_edge": best.avg_edge,
        "edges_by_h": {str(h): best.edges_by_h.get(h) for h in horizons},
        "selected_pair": {
            "from_symbol": selected_from,
            "to_symbol": best.to_symbol,
            "from_weight": from_weight,
            "robust_edge": best.robust_edge,
            "weighted_robust_edge": weighted_robust_edge,
            "avg_edge": best.avg_edge,
            "decision_metric": decision_metric,
            "edges_by_h": {str(h): best.edges_by_h.get(h) for h in horizons},
            "vetoed": best.vetoed,
            "veto_reason": best.veto_reason,
        },
        "delta_utility": best.robust_edge,
        "delta_blended": (
            round(
                float(candidate_components.get(best.to_symbol, {}).get("blend", 0.0))
                - float(weakest_held_blended),
                2,
            )
            if best.to_symbol in candidate_components
            else None
        ),
        "disagreement_veto_edge": veto_edge,
        "vetoed": best.vetoed,
        "veto_reason": best.veto_reason,
        "candidate_pairs": pair_diagnostics,
        "candidate_rows": candidate_rows,
        "held_components": held_components,
        "candidate_components": candidate_components,
        "utility_weights": utility_weights,
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

    if not (best.robust_edge >= thr and best.to_symbol != selected_from):
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

    w2 = apply_swap(w, selected_from, best.to_symbol)
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
            proposed_from=selected_from,
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
        from_symbol=selected_from,
        to_symbol=best.to_symbol,
        horizon_trading_days=horizon,
        target_trade_date=None,
        constraints_applied=applied,
        constraints_triggered=(),
        diagnostics=diagnostics,
    )
