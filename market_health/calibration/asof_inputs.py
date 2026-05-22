from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from market_health.calibration.market_data import (
    MarketDataDiagnostics,
    build_market_data_diagnostics,
)
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.warmup_window import (
    ReplayWarmupWindow,
    resolve_replay_warmup_window,
)

ASOF_INPUT_BUNDLE_SCHEMA_VERSION = "calibration_asof_input_bundle.v1"


@dataclass(frozen=True)
class AsOfInputBundle:
    replay_date: date
    lookback_rows: int
    requested_symbols: tuple[str, ...]
    eligible_symbols: tuple[str, ...]
    price_rows: tuple[HistoricalPriceRow, ...]
    warmup_window: ReplayWarmupWindow
    market_data_diagnostics: MarketDataDiagnostics
    excluded_future_row_count: int
    schema_version: str = ASOF_INPUT_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ASOF_INPUT_BUNDLE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported as-of input bundle schema version: {self.schema_version}"
            )
        if any(row.date > self.replay_date for row in self.price_rows):
            raise ValueError("as-of input bundle cannot contain future rows")

    @property
    def row_count(self) -> int:
        return len(self.price_rows)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "lookback_rows": self.lookback_rows,
            "requested_symbols": list(self.requested_symbols),
            "eligible_symbols": list(self.eligible_symbols),
            "row_count": self.row_count,
            "excluded_future_row_count": self.excluded_future_row_count,
            "market_data_diagnostics": self.market_data_diagnostics.to_record(),
        }


def build_asof_input_bundle(
    *,
    replay_date: date,
    symbols: Iterable[str],
    price_rows: Iterable[HistoricalPriceRow],
    lookback_rows: int,
) -> AsOfInputBundle:
    requested_symbols = _normalize_symbols(symbols)
    source_rows = tuple(price_rows)
    excluded_future_row_count = sum(
        1
        for row in source_rows
        if row.date > replay_date
        and (not requested_symbols or row.symbol in requested_symbols)
    )

    warmup_window = resolve_replay_warmup_window(
        source_rows,
        replay_date=replay_date,
        lookback_rows=lookback_rows,
        symbols=requested_symbols,
    )
    diagnostics = build_market_data_diagnostics(warmup_window)
    eligible_symbols = tuple(
        item.symbol for item in diagnostics.symbols if item.has_replay_date_row
    )

    return AsOfInputBundle(
        replay_date=replay_date,
        lookback_rows=lookback_rows,
        requested_symbols=requested_symbols,
        eligible_symbols=eligible_symbols,
        price_rows=warmup_window.rows,
        warmup_window=warmup_window,
        market_data_diagnostics=diagnostics,
        excluded_future_row_count=excluded_future_row_count,
    )


def _normalize_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()

    for symbol in symbols:
        value = symbol.strip().upper()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)

    return tuple(normalized)
