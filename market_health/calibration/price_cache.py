from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from market_health.calibration.defaults import assert_not_live_runtime_path

HISTORICAL_PRICE_CACHE_SCHEMA_VERSION = "historical_price_cache.v1"

HISTORICAL_PRICE_CACHE_COLUMNS = (
    "schema_version",
    "source",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)


@dataclass(frozen=True)
class HistoricalPriceRow:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
    source: str = "fixture"
    schema_version: str = HISTORICAL_PRICE_CACHE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("historical price row symbol is required")
        if self.schema_version != HISTORICAL_PRICE_CACHE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported historical price cache schema version: "
                f"{self.schema_version}"
            )
        if self.volume < 0:
            raise ValueError("historical price row volume must be non-negative")
        for name in ("open", "high", "low", "close", "adjusted_close"):
            if getattr(self, name) < 0:
                raise ValueError(f"historical price row {name} must be non-negative")

        object.__setattr__(self, "symbol", normalized_symbol)

    def to_record(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "symbol": self.symbol,
            "date": self.date.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "adjusted_close": str(self.adjusted_close),
            "volume": str(self.volume),
        }


@dataclass(frozen=True)
class HistoricalPriceCacheReadResult:
    rows: tuple[HistoricalPriceRow, ...]
    requested_symbols: tuple[str, ...]
    available_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    source_path: str
    start_date: date | None = None
    end_date: date | None = None


def historical_price_row_from_record(
    record: Mapping[str, str],
) -> HistoricalPriceRow:
    missing_columns = [
        column for column in HISTORICAL_PRICE_CACHE_COLUMNS if not record.get(column)
    ]
    if missing_columns:
        raise ValueError(
            "historical price cache row is missing required columns: "
            + ", ".join(missing_columns)
        )

    return HistoricalPriceRow(
        schema_version=record["schema_version"],
        source=record["source"],
        symbol=record["symbol"],
        date=date.fromisoformat(record["date"]),
        open=float(record["open"]),
        high=float(record["high"]),
        low=float(record["low"]),
        close=float(record["close"]),
        adjusted_close=float(record["adjusted_close"]),
        volume=int(record["volume"]),
    )


def read_historical_price_cache_csv(
    path: Path,
    *,
    symbols: Iterable[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> HistoricalPriceCacheReadResult:
    assert_not_live_runtime_path(path)

    requested_symbols = _normalize_requested_symbols(symbols)
    loaded_rows = _load_rows(path)
    _assert_unique_symbol_dates(loaded_rows)

    filtered_rows = []
    for row in loaded_rows:
        if requested_symbols and row.symbol not in requested_symbols:
            continue
        if start_date is not None and row.date < start_date:
            continue
        if end_date is not None and row.date > end_date:
            continue
        filtered_rows.append(row)

    rows = tuple(sorted(filtered_rows, key=lambda row: (row.symbol, row.date)))
    available_symbols = tuple(sorted({row.symbol for row in rows}))
    missing_symbols = tuple(
        symbol for symbol in requested_symbols if symbol not in available_symbols
    )

    return HistoricalPriceCacheReadResult(
        rows=rows,
        requested_symbols=requested_symbols,
        available_symbols=available_symbols,
        missing_symbols=missing_symbols,
        source_path=str(path),
        start_date=start_date,
        end_date=end_date,
    )


def _load_rows(path: Path) -> tuple[HistoricalPriceRow, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("historical price cache file has no header row")

        missing_columns = [
            column
            for column in HISTORICAL_PRICE_CACHE_COLUMNS
            if column not in reader.fieldnames
        ]
        if missing_columns:
            raise ValueError(
                "historical price cache file is missing required columns: "
                + ", ".join(missing_columns)
            )

        return tuple(historical_price_row_from_record(row) for row in reader)


def _normalize_requested_symbols(
    symbols: Iterable[str] | None,
) -> tuple[str, ...]:
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


def _assert_unique_symbol_dates(rows: Iterable[HistoricalPriceRow]) -> None:
    seen: set[tuple[str, date]] = set()
    for row in rows:
        key = (row.symbol, row.date)
        if key in seen:
            raise ValueError(
                "historical price cache contains duplicate symbol/date row: "
                f"{row.symbol} {row.date.isoformat()}"
            )
        seen.add(key)
