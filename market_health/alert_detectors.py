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


def _score_band(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value >= 70:
        return "green"
    if value >= 55:
        return "yellow"
    return "red"


def _band_rank(band: str) -> int:
    return {"unknown": 0, "red": 1, "yellow": 2, "green": 3}.get(band, 0)


def _is_band_worse(previous: Optional[float], current: Optional[float]) -> bool:
    return _band_rank(_score_band(current)) < _band_rank(_score_band(previous))


def detect_forecast_warnings(
    *,
    symbol: str,
    current_score: Optional[float],
    h1_score: Optional[float],
    h5_score: Optional[float],
    previous_h1_score: Optional[float] = None,
    previous_h5_score: Optional[float] = None,
    current_drop_threshold: float = 5.0,
    previous_drop_threshold: float = 7.0,
) -> List[AlertCandidate]:
    """Detect forecast deterioration for one held symbol."""

    normalized_symbol = str(symbol).strip().upper()
    if not normalized_symbol:
        return []

    alerts: List[AlertCandidate] = []

    horizon_values = {
        "H1": h1_score,
        "H5": h5_score,
    }
    previous_values = {
        "H1": previous_h1_score,
        "H5": previous_h5_score,
    }

    for horizon, forecast_score in horizon_values.items():
        if current_score is not None and forecast_score is not None:
            drop = float(current_score) - float(forecast_score)
            if drop >= current_drop_threshold:
                alerts.append(
                    AlertCandidate(
                        alert_key=f"forecast_warning:{normalized_symbol}:{horizon}:below_current",
                        alert_type="forecast_below_current",
                        severity="warning",
                        symbol=normalized_symbol,
                        title=f"{normalized_symbol} {horizon} forecast below current score",
                        message=(
                            f"{normalized_symbol} {horizon} forecast is {drop:.1f} points "
                            "below the current score."
                        ),
                        payload={
                            "symbol": normalized_symbol,
                            "horizon": horizon,
                            "current_score": float(current_score),
                            "forecast_score": float(forecast_score),
                            "drop": drop,
                            "threshold": float(current_drop_threshold),
                        },
                    )
                )

        previous_score = previous_values[horizon]
        if previous_score is not None and forecast_score is not None:
            weakening = float(previous_score) - float(forecast_score)
            if weakening >= previous_drop_threshold:
                alerts.append(
                    AlertCandidate(
                        alert_key=f"forecast_warning:{normalized_symbol}:{horizon}:weakened",
                        alert_type="forecast_weakened",
                        severity="warning",
                        symbol=normalized_symbol,
                        title=f"{normalized_symbol} {horizon} forecast weakened",
                        message=(
                            f"{normalized_symbol} {horizon} forecast weakened by "
                            f"{weakening:.1f} points since the previous snapshot."
                        ),
                        payload={
                            "symbol": normalized_symbol,
                            "horizon": horizon,
                            "previous_score": float(previous_score),
                            "forecast_score": float(forecast_score),
                            "weakening": weakening,
                            "threshold": float(previous_drop_threshold),
                        },
                    )
                )

            if _is_band_worse(previous_score, forecast_score):
                previous_band = _score_band(previous_score)
                current_band = _score_band(forecast_score)
                alerts.append(
                    AlertCandidate(
                        alert_key=f"forecast_warning:{normalized_symbol}:{horizon}:band_worse",
                        alert_type="forecast_band_worsened",
                        severity="warning",
                        symbol=normalized_symbol,
                        title=f"{normalized_symbol} {horizon} forecast band worsened",
                        message=(
                            f"{normalized_symbol} {horizon} forecast band worsened "
                            f"from {previous_band} to {current_band}."
                        ),
                        payload={
                            "symbol": normalized_symbol,
                            "horizon": horizon,
                            "previous_score": float(previous_score),
                            "forecast_score": float(forecast_score),
                            "previous_band": previous_band,
                            "current_band": current_band,
                        },
                    )
                )

    return alerts
