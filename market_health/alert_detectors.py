from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set


@dataclass(frozen=True)
class AlertCandidate:
    alert_key: str
    alert_type: str
    severity: str
    title: str
    message: str
    symbol: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


def _normalize_symbols(symbols: Iterable[str]) -> Set[str]:
    out: Set[str] = set()
    for symbol in symbols:
        text = str(symbol).strip().upper()
        if text:
            out.add(text)
    return out


def detect_position_inventory_changes(
    *,
    previous_symbols: Iterable[str],
    current_symbols: Iterable[str],
    suppress_first_run: bool = True,
) -> List[AlertCandidate]:
    """Detect held-position inventory changes between snapshots.

    This detector is intentionally pure and does not send notifications. The
    later runner/cooldown layer will decide whether candidates are stored,
    suppressed, or delivered.
    """

    previous = _normalize_symbols(previous_symbols)
    current = _normalize_symbols(current_symbols)

    if suppress_first_run and not previous:
        return []

    added = sorted(current - previous)
    removed = sorted(previous - current)

    alerts: List[AlertCandidate] = []

    for symbol in added:
        alerts.append(
            AlertCandidate(
                alert_key=f"position_inventory:added:{symbol}",
                alert_type="position_added",
                severity="info",
                symbol=symbol,
                title=f"New held position detected: {symbol}",
                message=f"{symbol} is present in the current held-position snapshot but was not present in the previous snapshot.",
                payload={
                    "symbol": symbol,
                    "previous_symbols": sorted(previous),
                    "current_symbols": sorted(current),
                },
            )
        )

    for symbol in removed:
        alerts.append(
            AlertCandidate(
                alert_key=f"position_inventory:removed:{symbol}",
                alert_type="position_removed",
                severity="warning",
                symbol=symbol,
                title=f"Held position removed: {symbol}",
                message=f"{symbol} was present in the previous held-position snapshot but is missing from the current snapshot.",
                payload={
                    "symbol": symbol,
                    "previous_symbols": sorted(previous),
                    "current_symbols": sorted(current),
                },
            )
        )

    if added or removed:
        alerts.append(
            AlertCandidate(
                alert_key="position_inventory:symbol_set_changed",
                alert_type="position_symbol_set_changed",
                severity="info" if added and not removed else "warning",
                title="Held position symbol set changed",
                message="The held-position symbol set changed between snapshots.",
                payload={
                    "added": added,
                    "removed": removed,
                    "previous_symbols": sorted(previous),
                    "current_symbols": sorted(current),
                },
            )
        )

    return alerts
