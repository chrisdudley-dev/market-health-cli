from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from market_health.calibration.price_cache import HistoricalPriceRow


@dataclass(frozen=True)
class ReplayWarmupWindow:
    replay_date: date
    lookback_rows: int
    rows: tuple[HistoricalPriceRow, ...]
    requested_symbols: tuple[str, ...]
    available_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    start_date: date | None
    end_date: date

    @property
    def row_count(self) -> int:
        return len(self.rows)


def resolve_replay_warmup_window(
    rows: Iterable[HistoricalPriceRow],
    *,
    replay_date: date,
    lookback_rows: int,
    symbols: Iterable[str] | None = None,
) -> ReplayWarmupWindow:
    """Select the last N available rows per symbol on or before replay date."""
    if lookback_rows <= 0:
        raise ValueError("lookback_rows must be positive")

    requested_symbols = _normalize_symbols(symbols)
    grouped: dict[str, list[HistoricalPriceRow]] = {}

    for row in rows:
        if row.date > replay_date:
            continue
        if requested_symbols and row.symbol not in requested_symbols:
            continue
        grouped.setdefault(row.symbol, []).append(row)

    selected_rows: list[HistoricalPriceRow] = []
    for symbol in sorted(grouped):
        symbol_rows = sorted(grouped[symbol], key=lambda item: item.date)
        selected_rows.extend(symbol_rows[-lookback_rows:])

    resolved_rows = tuple(
        sorted(selected_rows, key=lambda item: (item.symbol, item.date))
    )
    available_symbols = tuple(sorted(grouped))
    missing_symbols = tuple(
        symbol for symbol in requested_symbols if symbol not in available_symbols
    )
    start_date = min((row.date for row in resolved_rows), default=None)

    return ReplayWarmupWindow(
        replay_date=replay_date,
        lookback_rows=lookback_rows,
        rows=resolved_rows,
        requested_symbols=requested_symbols,
        available_symbols=available_symbols,
        missing_symbols=missing_symbols,
        start_date=start_date,
        end_date=replay_date,
    )


def _normalize_symbols(symbols: Iterable[str] | None) -> tuple[str, ...]:
    if symbols is None:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = symbol.strip().upper()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)

    return tuple(normalized)
