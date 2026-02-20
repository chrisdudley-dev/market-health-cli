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
    for _, cat in cats.items():
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


def recommend(*, positions: Any, scores: List[Dict[str, Any]], constraints: Dict[str, Any]) -> Recommendation:
    held = extract_held_symbols(positions)
    horizon = int(constraints.get("horizon_trading_days", 5) or 5)
    thr = float(constraints.get("min_improvement_threshold", 0.10))

    applied = ("min_improvement_threshold",)

    if not held:
        return Recommendation(
            action="NOOP",
            reason="No holdings found; nothing to rotate.",
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            diagnostics={"held": []},
        )

    s_map = utility_from_scores(scores)
    held_scored = [h for h in held if h in s_map]
    if not held_scored:
        return Recommendation(
            action="NOOP",
            reason="Holdings found but no matching score rows; cannot compute rotation.",
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            diagnostics={"held": held},
        )

    candidates = [sym for sym in s_map.keys() if sym not in set(held_scored)]
    if not candidates:
        return Recommendation(
            action="NOOP",
            reason="No candidates available beyond current holdings.",
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            diagnostics={"held_scored": held_scored},
        )

    weakest = sorted(held_scored, key=lambda sym: (s_map[sym]["utility"], stable_tiebreak_key(sym)))[0]
    best = sorted(candidates, key=lambda sym: (-s_map[sym]["utility"], stable_tiebreak_key(sym)))[0]

    u_from = float(s_map[weakest]["utility"])
    u_to = float(s_map[best]["utility"])
    delta = u_to - u_from

    diagnostics = {
        "weakest_holding": weakest,
        "best_candidate": best,
        "utility_from": u_from,
        "utility_to": u_to,
        "delta_utility": delta,
        "threshold": thr,
        "points_from": s_map[weakest]["points"],
        "max_points_from": s_map[weakest]["max_points"],
        "points_to": s_map[best]["points"],
        "max_points_to": s_map[best]["max_points"],
        "held_scored": held_scored,
        "candidates_n": len(candidates),
    }

    if delta >= thr and best != weakest:
        return Recommendation(
            action="SWAP",
            reason=f"{weakest} is weakest; {best} ranks higher with sufficient margin (Δ={delta:.3f} ≥ {thr:.3f}).",
            from_symbol=weakest,
            to_symbol=best,
            horizon_trading_days=horizon,
            target_trade_date=None,
            constraints_applied=applied,
            diagnostics=diagnostics,
        )

    return Recommendation(
        action="NOOP",
        reason=f"No candidate clears min improvement threshold (best Δ={delta:.3f} < {thr:.3f}); hold.",
        horizon_trading_days=horizon,
        target_trade_date=None,
        constraints_applied=applied,
        diagnostics=diagnostics,
    )
