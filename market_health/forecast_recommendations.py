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
from market_health.recommendation_weighting import (
    DEFAULT_UTILITY_WEIGHTS,
    DEFAULT_WEIGHTING_PROFILE,
    infer_symbol_family,
    resolve_utility_weights,
)

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

    def _score_node(sym: str, h):
        by_sym = scores.get(sym) if isinstance(scores, dict) else None
        if not isinstance(by_sym, dict):
            return {}
        node = by_sym.get(str(h))
        if not isinstance(node, dict):
            node = by_sym.get(h)
        return node if isinstance(node, dict) else {}

    def _f(val):
        try:
            if val is None:
                return None
            return float(val)
        except Exception:
            return None

    def _structure_summary(sym: str):
        node = _score_node(sym, 5)
        ss = node.get("structure_summary")
        return ss if isinstance(ss, dict) else {}

    current_utilities = constraints.get("current_utilities") or {}
    calibration_doc = constraints.get("calibration")
    weighting_profile = (
        constraints.get("weighting")
        or (
            calibration_doc.get("weighting")
            if isinstance(calibration_doc, dict)
            else None
        )
        or DEFAULT_WEIGHTING_PROFILE
    )
    base_utility_weights = (
        constraints.get("utility_weights")
        or (
            weighting_profile.get("base_utility_weights")
            if isinstance(weighting_profile, dict)
            else None
        )
        or DEFAULT_UTILITY_WEIGHTS
    )
    regime_key = (
        constraints.get("regime_key")
        or (
            calibration_doc.get("regime_key")
            if isinstance(calibration_doc, dict)
            else None
        )
        or "neutral"
    )
    symbol_family_by_symbol = constraints.get("symbol_family_by_symbol") or {}
    weighting_source = (
        constraints.get("calibration_source")
        or (
            calibration_doc.get("source") if isinstance(calibration_doc, dict) else None
        )
        or "defaults"
    )

    def _weight_context(sym: str):
        explicit_family = None
        if isinstance(symbol_family_by_symbol, dict):
            raw_family = symbol_family_by_symbol.get(sym)
            if isinstance(raw_family, str) and raw_family.strip():
                explicit_family = raw_family.strip().lower()

        family = explicit_family or infer_symbol_family(sym)
        return resolve_utility_weights(
            base_weights=base_utility_weights,
            weighting_profile=weighting_profile,
            regime_key=regime_key,
            symbol_family=family,
        )

    def _current_score(sym: str):
        cu = current_utilities.get(sym) if isinstance(current_utilities, dict) else None
        if isinstance(cu, dict):
            val = _f(cu.get("utility"))
            if val is not None:
                return val

        by_sym = scores.get(sym) if isinstance(scores, dict) else None
        if not isinstance(by_sym, dict):
            return None

        search_order = ("0", 0, "1", 1, "5", 5)
        keys = (
            "current_score",
            "spot_score",
            "base_score",
            "health_score_current",
            "current_health_score",
            "current",
            "c",
        )
        for h in search_order:
            node = _score_node(sym, h)
            if not isinstance(node, dict):
                continue
            for key in keys:
                val = _f(node.get(key))
                if val is not None:
                    return val
        return None

    def _forecast_score(sym: str, h: int):
        node = _score_node(sym, h)
        if not isinstance(node, dict):
            return None
        for key in ("forecast_score", "health_score", "score"):
            val = _f(node.get(key))
            if val is not None:
                return val
        return None

    def _blend(sym: str, c, h1, h5):
        resolved_weights = _weight_context(sym).get("weights") or {}
        weighted = []
        for key, val in (("c", c), ("h1", h1), ("h5", h5)):
            n = _f(val)
            w = _f(resolved_weights.get(key))
            if n is None or w is None or w <= 0:
                continue
            weighted.append((n, w))

        if weighted:
            num = sum(v * w for v, w in weighted)
            den = sum(w for _, w in weighted)
            return None if den <= 0 else (num / den)

        vals = [v for v in (c, h1, h5) if v is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    def _state_tags(sym: str):
        ss = _structure_summary(sym)
        tags = ss.get("state_tags")
        if isinstance(tags, (list, tuple)):
            return [str(t) for t in tags]
        return []

    def _component_map(sym: str):
        c = _current_score(sym)
        h1 = _forecast_score(sym, 1)
        h5 = _forecast_score(sym, 5)
        blend = _blend(sym, c, h1, h5)
        ss = _structure_summary(sym)
        sup = _f(ss.get("support_cushion_atr"))
        res = _f(ss.get("overhead_resistance_atr"))
        tags = _state_tags(sym)

        return {
            "symbol": sym,
            "blend": blend,
            "blended": blend,
            "c": c,
            "current": c,
            "h1": h1,
            "h5": h5,
            "delta_1": None if c is None or h1 is None else (h1 - c),
            "delta_5": None if c is None or h5 is None else (h5 - c),
            "support_cushion_atr": sup,
            "overhead_resistance_atr": res,
            "state_tags": tags,
            "effective_utility_weights": _weight_context(sym).get("weights"),
            "symbol_family": _weight_context(sym).get("symbol_family"),
        }

    held_components = {sym: _component_map(sym) for sym in held_present}
    candidate_components = {sym: _component_map(sym) for sym in candidates}

    weakest_components = held_components.get(weakest) or _component_map(weakest)
    weakest_blend = _f(weakest_components.get("blended"))

    def _pair_row(row):
        from_comp = held_components.get(weakest) or _component_map(weakest)
        to_comp = candidate_components.get(row.to_symbol) or _component_map(
            row.to_symbol
        )
        weighted = _f(getattr(row, "weighted_robust_edge", None))
        if weighted is None:
            weighted = _f(row.robust_edge)

        return {
            "from_symbol": weakest,
            "to_symbol": row.to_symbol,
            "from_blend": _f(from_comp.get("blended")),
            "to_blend": _f(to_comp.get("blended")),
            "robust_edge": _f(row.robust_edge),
            "weighted_robust_edge": weighted,
            "avg_edge": _f(row.avg_edge),
            "edges_by_h": {str(h): row.edges_by_h.get(h) for h in horizons},
            "vetoed": bool(row.vetoed),
            "veto_reason": row.veto_reason,
        }

    candidate_pairs = [_pair_row(row) for row in ranked]
    selected_pair = candidate_pairs[0] if candidate_pairs else {}

    candidate_rows = []
    for row in ranked:
        comp = candidate_components.get(row.to_symbol) or _component_map(row.to_symbol)
        cand_blend = _f(comp.get("blended"))
        delta_blend = None
        if weakest_blend is not None and cand_blend is not None:
            delta_blend = cand_blend - weakest_blend

        robust_edge = _f(row.robust_edge)
        vetoed = bool(row.vetoed)
        status = (
            "BLOCKED" if vetoed or robust_edge is None or robust_edge < thr else "READY"
        )

        candidate_rows.append(
            {
                "symbol": row.to_symbol,
                "blend": cand_blend,
                "blended": cand_blend,
                "c": _f(comp.get("current")),
                "current": _f(comp.get("current")),
                "h1": _f(comp.get("h1")),
                "h5": _f(comp.get("h5")),
                "delta_blend": delta_blend,
                "delta_utility": robust_edge,
                "edge": robust_edge,
                "threshold": thr,
                "status": status,
                "vetoed": vetoed,
                "veto_reason": row.veto_reason,
                "support_cushion_atr": _f(comp.get("support_cushion_atr")),
                "overhead_resistance_atr": _f(comp.get("overhead_resistance_atr")),
                "state_tags": list(comp.get("state_tags") or []),
            }
        )

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
        "utility_weights": base_utility_weights,
        "weighting_regime": regime_key,
        "weighting_profile_source": weighting_source,
        "symbol_families": {
            sym: _weight_context(sym).get("symbol_family")
            for sym in sorted(set(held_present + candidates), key=stable_tiebreak_key)
        },
        "effective_utility_weights_by_symbol": {
            sym: _weight_context(sym).get("weights")
            for sym in sorted(set(held_present + candidates), key=stable_tiebreak_key)
        },
        "held_components": held_components,
        "candidate_components": candidate_components,
        "candidate_rows": candidate_rows,
        "candidate_pairs": candidate_pairs,
        "selected_pair": selected_pair,
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
