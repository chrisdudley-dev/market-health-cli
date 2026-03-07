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
    Constraints v0:
      - min_improvement_threshold: SWAP only if best candidate improves utility by >= threshold
      - max_swaps_per_day + swaps_today: NOOP if swap quota reached
      - turnover_cap: NOOP if 1/len(held) > cap
      - sector_cap: NOOP if sector concentration would exceed cap (requires row["sector"] present)
    """
    horizon = int(constraints.get("horizon_trading_days", 5) or 5)
    thr = float(constraints.get("min_improvement_threshold", 0.12))

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

    applied_list = ["min_improvement_threshold", "max_swaps_per_day"]
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
            diagnostics={"threshold": thr, "horizon_trading_days": horizon},
        )

    util = blended_utility_from_scores(
        scores,
        forecast_scores=constraints.get("forecast_scores"),
        utility_weights=constraints.get("utility_weights"),
        forecast_horizons=constraints.get("forecast_horizons") or (1, 5),
    )

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
                "threshold": thr,
                "horizon_trading_days": horizon,
                "held": held,
            },
        )

    # weakest held by utility, stable tiebreak
    weakest = min(
        held_present,
        key=lambda s: (float(util[s].get("utility", 0.0)), stable_tiebreak_key(s)),
    )

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
                "threshold": thr,
                "horizon_trading_days": horizon,
                "held": held_present,
            },
        )

    # Choose best candidate by utility; break ties deterministically (alphabetical via stable_tiebreak_key)
    best_u = max(float(util[s].get("utility", 0.0)) for s in candidates)
    best_cands = [s for s in candidates if float(util[s].get("utility", 0.0)) == best_u]
    best = min(best_cands, key=stable_tiebreak_key)
    delta = float(util[best].get("utility", 0.0)) - float(
        util[weakest].get("utility", 0.0)
    )


    # BLENDED_CANDIDATE_ROWS_V1
    candidate_rows = []
    weakest_blended = float(util[weakest].get("utility", 0.0))
    weakest_current = util[weakest].get("current_utility")
    weakest_h1 = util[weakest].get("h1_utility")
    weakest_h5 = util[weakest].get("h5_utility")

    for sym, meta in sorted(
        ((s, util[s]) for s in candidates),
        key=lambda kv: float(kv[1].get("utility", 0.0)),
        reverse=True,
    ):
        blended = float(meta.get("utility", 0.0))
        c_util = meta.get("current_utility")
        h1_util = meta.get("h1_utility")
        h5_util = meta.get("h5_utility")
        candidate_rows.append(
            {
                "sym": sym,
                "blended": blended,
                "c": c_util,
                "h1": h1_util,
                "h5": h5_util,
                "delta_blended": blended - weakest_blended,
                "threshold": thr,
                "status": "READY" if (blended - weakest_blended) >= thr else "BLOCKED",
            }
        )

    diagnostics = {
        "threshold": thr,
        "horizon_trading_days": horizon,
        "weakest_held": weakest,
        "best_candidate": best,
        "utility_weights": dict(util[best].get("utility_weights", {})),
        "delta_utility": delta,
        "decision_metric": "blended_utility",
        "edge": delta,
        "health_score_from": float(util[weakest].get("utility", 0.0)),
        "health_score_to": float(util[best].get("utility", 0.0)),
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
        "candidate_utility": float(util[best].get("utility", 0.0)),
        "candidate_components": {
            "c": util[best].get("current_utility"),
            "h1": util[best].get("h1_utility"),
            "h5": util[best].get("h5_utility"),
            "blended": util[best].get("utility"),
        },
        "candidate_rows": candidate_rows,
    }

    # base threshold gate
    if not (delta >= thr and best != weakest):
        return Recommendation(
            action="NOOP",
            reason=(
                f"No candidate clears min improvement threshold "
                f"(best blended Δ={delta:.3f} < {thr:.3f}); hold."
            ),
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            constraints_triggered=("min_improvement_threshold",),
            diagnostics=diagnostics,
        )

    triggered: List[str] = []

    # max swaps/day
    if swaps_today >= max_swaps:
        triggered.append("max_swaps_per_day")

    # turnover cap
    if turnover_cap is not None:
        turnover = 1.0 / max(1, len(held_present))
        if turnover > turnover_cap:
            triggered.append("turnover_cap")
        diagnostics["turnover"] = turnover
        diagnostics["turnover_cap"] = turnover_cap

    # sector cap (only if sector info exists)
    if sector_cap is not None:
        sym_sector: Dict[str, str] = {}
        for row in scores:
            if not isinstance(row, dict):
                continue
            sym = row.get("symbol")
            sec = row.get("sector")
            if isinstance(sym, str) and sym and isinstance(sec, str) and sec:
                sym_sector[sym.strip().upper()] = sec.strip()

        cand_sec = sym_sector.get(best)
        if cand_sec:
            held_counts: Dict[str, int] = {}
            for h in held_present:
                hs = sym_sector.get(h)
                if hs:
                    held_counts[hs] = held_counts.get(hs, 0) + 1

            worst_sec = sym_sector.get(weakest)
            post = held_counts.get(cand_sec, 0) + (0 if worst_sec == cand_sec else 1)
            diagnostics["sector_cap"] = sector_cap
            diagnostics["candidate_sector"] = cand_sec
            diagnostics["post_sector_count"] = post
            if post > sector_cap:
                triggered.append("sector_cap")

    if triggered:
        diag2 = dict(diagnostics)
        diag2.update(
            {
                "constraints_triggered": list(triggered),
                "swaps_today": swaps_today,
                "max_swaps_per_day": max_swaps,
            }
        )
        return Recommendation(
            action="NOOP",
            reason="Swap blocked by constraints: " + ", ".join(triggered) + "; hold.",
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            constraints_triggered=tuple(triggered),
            diagnostics=diag2,
        )

    return Recommendation(
        action="SWAP",
        reason=f"{weakest} is weakest; {best} ranks higher with sufficient margin (Δ={delta:.3f} ≥ {thr:.3f}).",
        from_symbol=weakest,
        to_symbol=best,
        horizon_trading_days=horizon,
        target_trade_date=None,
        constraints_applied=applied,
        constraints_triggered=(),
        diagnostics=diagnostics,
    )
