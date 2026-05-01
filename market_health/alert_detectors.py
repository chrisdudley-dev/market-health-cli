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


def _normalize_state_tokens(value: Optional[str]) -> Set[str]:
    if value is None:
        return set()

    text = str(value).strip()
    if not text:
        return set()

    parts = text.replace(",", " ").replace("|", " ").replace(";", " ").split()
    tokens: Set[str] = set()
    for part in parts:
        token = part.strip().upper()
        if not token or token in {"-", "—", "CLEAN", "OK", "NONE", "NULL", "N/A"}:
            continue
        tokens.add(token)
    return tokens


def detect_position_state_changes(
    *,
    previous_states: Dict[str, Optional[str]],
    current_states: Dict[str, Optional[str]],
) -> List[AlertCandidate]:
    """Detect meaningful state transitions for symbols present in both snapshots."""

    previous_by_symbol = {
        str(symbol).strip().upper(): state
        for symbol, state in previous_states.items()
        if str(symbol).strip()
    }
    current_by_symbol = {
        str(symbol).strip().upper(): state
        for symbol, state in current_states.items()
        if str(symbol).strip()
    }

    alerts: List[AlertCandidate] = []
    for symbol in sorted(set(previous_by_symbol) & set(current_by_symbol)):
        previous_tokens = _normalize_state_tokens(previous_by_symbol[symbol])
        current_tokens = _normalize_state_tokens(current_by_symbol[symbol])

        if previous_tokens == current_tokens:
            continue

        added = sorted(current_tokens - previous_tokens)
        removed = sorted(previous_tokens - current_tokens)

        if current_tokens and not previous_tokens:
            severity = "warning"
        elif not current_tokens and previous_tokens:
            severity = "info"
        elif added:
            severity = "warning"
        else:
            severity = "info"

        previous_label = ",".join(sorted(previous_tokens)) or "clean"
        current_label = ",".join(sorted(current_tokens)) or "clean"

        alerts.append(
            AlertCandidate(
                alert_key=f"position_state:{symbol}:{previous_label}->{current_label}",
                alert_type="position_state_changed",
                severity=severity,
                symbol=symbol,
                title=f"{symbol} state changed: {previous_label} -> {current_label}",
                message=f"{symbol} state changed from {previous_label} to {current_label}.",
                payload={
                    "symbol": symbol,
                    "previous_state": previous_label,
                    "current_state": current_label,
                    "added_tags": added,
                    "removed_tags": removed,
                },
            )
        )

    return alerts
