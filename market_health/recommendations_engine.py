"""market_health.recommendations_engine

RECOMMENDATIONS / ROTATION ENGINE (M8.2)

Deterministic v0:
- SWAP: weakest held -> best candidate, if improvement clears threshold
- NOOP: otherwise (with explicit reason)

Inputs:
- positions: positions.v1-like dict (or list of symbols)
- scores: list[dict] rows (compute_scores output OR cached sectors rows)
- constraints: dict (v0 uses min_improvement_threshold + horizon_trading_days)

Pure/deterministic: no IO, no network, no timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple


Action = Literal["SWAP", "NOOP"]


@dataclass(frozen=True)
class Recommendation:
    action: Action
    reason: str

    # SWAP fields
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


def _forecast_utility(payload: Any) -> Optional[float]:
    if not isinstance(payload, dict):
        return None

    fs = payload.get("forecast_score")
    if isinstance(fs, (int, float)):
        val = float(fs)
        return (val / 100.0) if val > 1.5 else val

    pts = payload.get("points")
    mx = payload.get("max_points")
    if isinstance(pts, (int, float)) and isinstance(mx, (int, float)) and mx:
        return float(pts) / float(mx)

    return None


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
        h1_util = _forecast_utility(_forecast_payload_for(forecast_scores, sym, h1))
        h5_util = _forecast_utility(_forecast_payload_for(forecast_scores, sym, h5))

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


def recommend(
    *, positions: Any, scores: List[Dict[str, Any]], constraints: Dict[str, Any]
) -> Recommendation:
    """
    Constraints:
      - min_delta / min_improvement_threshold: SWAP only if best candidate improves utility by >= threshold
      - min_floor: candidate absolute utility floor required for normal replacement
      - sgov_symbol + sgov_is_policy_fallback: use SGOV as deterministic fallback when enabled
      - max_precious_holdings: maximum simultaneous PRECIOUS holdings after the swap
      - block_gltr_component_overlap: block GLTR plus single-metal overlap in v1
      - max_swaps_per_day + swaps_today: NOOP if swap quota reached
      - turnover_cap: NOOP if 1/len(held) > cap
      - sector_cap: NOOP if sector concentration would exceed cap (requires row["sector"] present)
    """
    if bool(constraints.get("forecast_mode", False)):
        from market_health.forecast_recommendations import recommend_forecast_mode

        return recommend_forecast_mode(positions=positions, constraints=constraints)

    horizon = int(constraints.get("horizon_trading_days", 5) or 5)

    min_delta_raw = constraints.get(
        "min_delta", constraints.get("min_improvement_threshold", 0.12)
    )
    min_delta = float(min_delta_raw if min_delta_raw not in (None, "") else 0.12)

    min_floor_raw = constraints.get(
        "min_floor", constraints.get("candidate_min_floor", 0.0)
    )
    min_floor = float(min_floor_raw if min_floor_raw not in (None, "") else 0.0)

    sgov_symbol = str(constraints.get("sgov_symbol", "SGOV") or "SGOV").strip().upper()
    sgov_is_policy_fallback = bool(constraints.get("sgov_is_policy_fallback", False))

    max_precious_raw = constraints.get("max_precious_holdings", 1)
    max_precious_holdings = int(
        max_precious_raw if max_precious_raw not in (None, "") else 1
    )
    block_gltr_component_overlap = bool(
        constraints.get("block_gltr_component_overlap", False)
    )

    max_swaps = int(constraints.get("max_swaps_per_day", 1) or 1)
    swaps_today = int(constraints.get("swaps_today", 0) or 0)

    sector_cap_raw = constraints.get("sector_cap")
    sector_cap = int(sector_cap_raw) if sector_cap_raw not in (None, "") else None

    turnover_cap_raw = constraints.get("turnover_cap") or constraints.get(
        "max_turnover_fraction"
    )
    turnover_cap = (
        float(turnover_cap_raw) if turnover_cap_raw not in (None, "") else None
    )

    applied_list = ["min_delta", "max_swaps_per_day"]
    if min_floor > 0:
        applied_list.append("min_floor")
    if sgov_is_policy_fallback:
        applied_list.append("sgov_policy_fallback")
    applied_list.append("max_precious_holdings")
    if block_gltr_component_overlap:
        applied_list.append("block_gltr_component_overlap")
    if sector_cap is not None:
        applied_list.append("sector_cap")
    if turnover_cap is not None:
        applied_list.append("turnover_cap")
    applied = tuple(applied_list)

    held = [s.upper() for s in extract_held_symbols(positions)]
    if not held:
        return Recommendation(
            action="NOOP",
            reason="No held symbols found; nothing to do.",
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            constraints_triggered=(),
            diagnostics={
                "min_delta": min_delta,
                "min_floor": min_floor,
                "horizon_trading_days": horizon,
            },
        )

    util = blended_utility_from_scores(
        scores,
        forecast_scores=constraints.get("forecast_scores"),
        utility_weights=constraints.get("utility_weights"),
        forecast_horizons=constraints.get("forecast_horizons") or (1, 5),
    )

    row_meta: Dict[str, Dict[str, Any]] = {}
    sym_sector: Dict[str, str] = {}
    for row in scores:
        if not isinstance(row, dict):
            continue
        sym = row.get("symbol")
        if not isinstance(sym, str) or not sym.strip():
            continue
        sym_u = sym.strip().upper()
        row_meta[sym_u] = {
            "asset_type": row.get("asset_type"),
            "group": row.get("group"),
            "metal_type": row.get("metal_type"),
            "is_basket": row.get("is_basket"),
        }
        sec = row.get("sector")
        if isinstance(sec, str) and sec.strip():
            sym_sector[sym_u] = sec.strip().upper()

    held_present = [h for h in held if h in util]
    if not held_present:
        return Recommendation(
            action="NOOP",
            reason="Held symbols not found in scored universe; cannot compare.",
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            constraints_triggered=(),
            diagnostics={
                "min_delta": min_delta,
                "min_floor": min_floor,
                "horizon_trading_days": horizon,
                "held": held,
            },
        )

    weakest = min(
        held_present,
        key=lambda s: (float(util[s].get("utility", 0.0)), stable_tiebreak_key(s)),
    )
    weakest_blended = float(util[weakest].get("utility", 0.0))

    candidates = [s for s in util.keys() if s not in set(held_present)]
    if not candidates:
        return Recommendation(
            action="NOOP",
            reason="No candidates available outside held set.",
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            constraints_triggered=(),
            diagnostics={
                "min_delta": min_delta,
                "min_floor": min_floor,
                "horizon_trading_days": horizon,
                "held": held_present,
            },
        )

    def _candidate_sort_key(sym: str) -> Tuple[float, Tuple[str]]:
        return (-float(util[sym].get("utility", 0.0)), stable_tiebreak_key(sym))

    def _is_precious(sym: str) -> bool:
        return row_meta.get(sym, {}).get("group") == "PRECIOUS"

    def _after_swap_precious(candidate: str) -> List[str]:
        after = [h for h in held_present if h != weakest and _is_precious(h)]
        if _is_precious(candidate):
            after.append(candidate)
        return after

    def _policy_reasons(candidate: str) -> List[str]:
        reasons: List[str] = []
        if not _is_precious(candidate):
            return reasons

        after_precious = _after_swap_precious(candidate)

        if len(after_precious) > max_precious_holdings:
            reasons.append("policy:max_precious_holdings")

        if block_gltr_component_overlap:
            after_metals = [
                row_meta.get(sym, {}).get("metal_type") for sym in after_precious
            ]
            has_basket = any(m == "basket" for m in after_metals)
            has_single = any(
                isinstance(m, str) and m not in {"basket"} for m in after_metals
            )
            if has_basket and has_single:
                reasons.append("policy:block_gltr_component_overlap")

        return reasons

    candidate_rows: List[Dict[str, Any]] = []
    candidate_row_index: Dict[str, Dict[str, Any]] = {}
    normal_candidates = [s for s in candidates if s != sgov_symbol]

    for sym in sorted(candidates, key=_candidate_sort_key):
        meta = util[sym]
        blended = float(meta.get("utility", 0.0))
        delta_blended = blended - weakest_blended

        reasons: List[str] = []
        passes_floor = None
        passes_delta = None
        passes_policy = None

        if sym == sgov_symbol:
            reasons.append("fallback_only")
        else:
            passes_floor = blended >= min_floor
            passes_delta = delta_blended >= min_delta
            policy_reasons = _policy_reasons(sym)
            passes_policy = len(policy_reasons) == 0

            if not passes_floor:
                reasons.append("below_floor")
            if not passes_delta:
                reasons.append("below_delta")
            reasons.extend(policy_reasons)

        reasons = list(dict.fromkeys(reasons))
        row = {
            "sym": sym,
            "blended": blended,
            "c": meta.get("current_utility"),
            "h1": meta.get("h1_utility"),
            "h5": meta.get("h5_utility"),
            "delta_blended": delta_blended,
            "threshold": min_delta,
            "min_floor": min_floor,
            "passes_floor": passes_floor,
            "passes_delta": passes_delta,
            "passes_policy": passes_policy,
            "status": "READY"
            if not reasons
            else ("FALLBACK_ONLY" if sym == sgov_symbol else "BLOCKED"),
            "rejection_reasons": reasons,
            "asset_type": row_meta.get(sym, {}).get("asset_type"),
            "group": row_meta.get(sym, {}).get("group"),
            "metal_type": row_meta.get(sym, {}).get("metal_type"),
            "is_basket": row_meta.get(sym, {}).get("is_basket"),
        }
        candidate_rows.append(row)
        candidate_row_index[sym] = row

    best_normal = (
        sorted(normal_candidates, key=_candidate_sort_key)[0]
        if normal_candidates
        else None
    )

    utility_weights_source = util.get(best_normal or weakest, {})
    diagnostics = {
        "min_delta": min_delta,
        "min_floor": min_floor,
        "threshold": min_delta,
        "horizon_trading_days": horizon,
        "weakest_held": weakest,
        "best_candidate": best_normal,
        "utility_weights": dict(utility_weights_source.get("utility_weights", {})),
        "decision_metric": "blended_utility",
        "edge": None,
        "delta_utility": None,
        "health_score_from": float(util[weakest].get("utility", 0.0)),
        "health_score_to": (
            float(util[best_normal].get("utility", 0.0)) if best_normal else None
        ),
        "held": held,
        "held_scored": held_present,
        "held_utilities": {h: float(util[h].get("utility", 0.0)) for h in held_present},
        "held_components": {
            h: {
                "c": util[h].get("current_utility"),
                "h1": util[h].get("h1_utility"),
                "h5": util[h].get("h5_utility"),
                "blended": util[h].get("utility"),
            }
            for h in held_present
        },
        "candidate_utility": (
            float(util[best_normal].get("utility", 0.0)) if best_normal else None
        ),
        "candidate_components": (
            {
                "c": util[best_normal].get("current_utility"),
                "h1": util[best_normal].get("h1_utility"),
                "h5": util[best_normal].get("h5_utility"),
                "blended": util[best_normal].get("utility"),
            }
            if best_normal
            else {}
        ),
        "candidate_rows": candidate_rows,
    }

    if best_normal is not None:
        delta = float(util[best_normal].get("utility", 0.0)) - weakest_blended
        diagnostics["delta_utility"] = delta
        diagnostics["edge"] = delta

    if turnover_cap is not None:
        turnover = 1.0 / max(1, len(held_present))
        diagnostics["turnover"] = turnover
        diagnostics["turnover_cap"] = turnover_cap

    def _apply_global_constraints(target_symbol: str) -> List[str]:
        triggered: List[str] = []

        if swaps_today >= max_swaps:
            triggered.append("max_swaps_per_day")

        if turnover_cap is not None:
            turnover = 1.0 / max(1, len(held_present))
            if turnover > turnover_cap:
                triggered.append("turnover_cap")

        if sector_cap is not None:
            cand_sec = sym_sector.get(target_symbol)
            if cand_sec:
                held_counts: Dict[str, int] = {}
                for h in held_present:
                    hs = sym_sector.get(h)
                    if hs:
                        held_counts[hs] = held_counts.get(hs, 0) + 1

                worst_sec = sym_sector.get(weakest)
                post = held_counts.get(cand_sec, 0) + (
                    0 if worst_sec == cand_sec else 1
                )

                diagnostics["sector_cap"] = sector_cap
                diagnostics["candidate_sector"] = cand_sec
                diagnostics["post_sector_count"] = post

                if post > sector_cap:
                    triggered.append("sector_cap")

        return list(dict.fromkeys(triggered))

    def _append_constraint_reasons(sym: str, triggered: List[str]) -> None:
        row = candidate_row_index.get(sym)
        if not row:
            return
        reasons = list(row.get("rejection_reasons") or [])
        for name in triggered:
            tag = f"constraint:{name}"
            if tag not in reasons:
                reasons.append(tag)
        row["rejection_reasons"] = reasons
        row["status"] = "BLOCKED"

    best_ready = next(
        (
            sym
            for sym in sorted(normal_candidates, key=_candidate_sort_key)
            if not candidate_row_index[sym]["rejection_reasons"]
        ),
        None,
    )

    if best_ready is not None:
        triggered = _apply_global_constraints(best_ready)
        if triggered:
            _append_constraint_reasons(best_ready, triggered)
            diagnostics["selection_mode"] = "best_candidate_blocked"
            diagnostics["fallback_reason"] = None
            return Recommendation(
                action="NOOP",
                reason="Swap blocked by constraints: " + ", ".join(triggered) + ".",
                horizon_trading_days=horizon,
                target_trade_date=None,
                constraints_applied=applied,
                constraints_triggered=tuple(triggered),
                diagnostics=diagnostics,
            )

        delta = float(util[best_ready].get("utility", 0.0)) - weakest_blended
        diagnostics["selection_mode"] = "best_candidate"
        diagnostics["fallback_reason"] = None
        diagnostics["best_candidate"] = best_ready
        diagnostics["candidate_utility"] = float(util[best_ready].get("utility", 0.0))
        diagnostics["candidate_components"] = {
            "c": util[best_ready].get("current_utility"),
            "h1": util[best_ready].get("h1_utility"),
            "h5": util[best_ready].get("h5_utility"),
            "blended": util[best_ready].get("utility"),
        }
        diagnostics["delta_utility"] = delta
        diagnostics["edge"] = delta

        return Recommendation(
            action="SWAP",
            reason=(
                f"Best candidate clears min floor and min delta "
                f"(best blended Δ={delta:.3f}); swap."
            ),
            from_symbol=weakest,
            to_symbol=best_ready,
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            constraints_triggered=(),
            diagnostics=diagnostics,
        )

    def _fallback_reason() -> str:
        normal_rows = [
            candidate_row_index[s]
            for s in normal_candidates
            if s in candidate_row_index
        ]
        if not normal_rows:
            return "no_candidate_rows"

        any_policy_blocked = any(
            bool(r.get("passes_floor"))
            and bool(r.get("passes_delta"))
            and (r.get("passes_policy") is False)
            for r in normal_rows
        )
        if any_policy_blocked:
            return "policy_blocked"

        return "no_candidate_clears_floor_and_delta"

    fallback_reason = _fallback_reason()

    if sgov_is_policy_fallback and sgov_symbol in candidates:
        triggered = _apply_global_constraints(sgov_symbol)
        if triggered:
            _append_constraint_reasons(sgov_symbol, triggered)
            diagnostics["selection_mode"] = "sgov_fallback_blocked"
            diagnostics["fallback_reason"] = fallback_reason
            return Recommendation(
                action="NOOP",
                reason="SGOV fallback blocked by constraints: "
                + ", ".join(triggered)
                + ".",
                horizon_trading_days=horizon,
                target_trade_date=None,
                constraints_applied=applied,
                constraints_triggered=tuple(triggered),
                diagnostics=diagnostics,
            )

        diagnostics["selection_mode"] = (
            "sgov_fallback"
            if fallback_reason == "policy_blocked"
            else "policy_fallback"
        )
        diagnostics["fallback_reason"] = fallback_reason
        return Recommendation(
            action="SWAP",
            reason=f"No candidate clears policy gates; fallback to {sgov_symbol}.",
            from_symbol=weakest,
            to_symbol=sgov_symbol,
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            constraints_triggered=(),
            diagnostics=diagnostics,
        )

    diagnostics["selection_mode"] = "no_swap"
    diagnostics["fallback_reason"] = fallback_reason

    if best_normal is None:
        reason = "No candidates available outside held set."
        triggered = ()
    else:
        reasons = (
            candidate_row_index.get(best_normal, {}).get("rejection_reasons") or []
        )
        triggered = tuple(
            r for r in reasons if isinstance(r, str) and r.startswith("policy:")
        )

        if "below_floor" in reasons and "below_delta" in reasons:
            reason = (
                f"No candidate clears min floor ({min_floor:.3f}) and "
                f"min delta ({min_delta:.3f}); hold."
            )
        elif "below_floor" in reasons:
            reason = f"No candidate clears min floor ({min_floor:.3f}); hold."
        elif "below_delta" in reasons:
            reason = f"No candidate clears min delta ({min_delta:.3f}); hold."
        elif reasons:
            reason = "Best candidate blocked by policy: " + ", ".join(reasons) + "."
        else:
            reason = "No eligible replacement candidate found; hold."

    return Recommendation(
        action="NOOP",
        reason=reason,
        horizon_trading_days=horizon,
        target_trade_date=None,
        constraints_applied=applied,
        constraints_triggered=triggered,
        diagnostics=diagnostics,
    )
