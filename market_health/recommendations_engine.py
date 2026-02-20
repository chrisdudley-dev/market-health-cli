"""market_health.recommendations_engine

RECOMMENDATIONS / ROTATION ENGINE (M8.2)

This module will produce deterministic recommendation outputs (SWAP vs NOOP)
based on current positions + computed scores + constraints.

Important: keep this module PURE and deterministic:
- no file IO
- no network calls
- no reading ~/.cache
- no side effects

Writers/exporters/wiring will live elsewhere (scripts/jerboa/*).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Tuple


Action = Literal["SWAP", "NOOP"]


@dataclass(frozen=True)
class Recommendation:
    action: Action
    reason: str
    # For SWAP
    from_symbol: Optional[str] = None
    to_symbol: Optional[str] = None
    # Scheduling fields (filled later; tracked in M9 too)
    horizon_trading_days: Optional[int] = None
    target_trade_date: Optional[str] = None  # YYYY-MM-DD
    # Auditing / explainability
    constraints_applied: Tuple[str, ...] = ()


def stable_tiebreak_key(symbol: str) -> Tuple[str]:
    """Deterministic tie-break key for stable ordering."""
    return (symbol.upper(),)


def recommend(
    *,
    positions: Dict[str, Any],
    scores: Dict[str, Any],
    constraints: Dict[str, Any],
) -> Recommendation:
    """Return a deterministic SWAP or NOOP recommendation (placeholder).

    This stub intentionally returns NOOP until M8.2 implements full logic.
    """
    _ = (positions, scores, constraints)
    return Recommendation(action="NOOP", reason="recommendations_engine not implemented yet")
