from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.warmup_window import ReplayWarmupWindow

MARKET_DATA_DIAGNOSTICS_SCHEMA_VERSION = "calibration_market_data_diagnostics.v1"


@dataclass(frozen=True)
class MarketDataSymbolDiagnostic:
    symbol: str
    available_rows: int
    has_replay_date_row: bool
    is_missing_symbol: bool
    is_partial_warmup: bool

    def to_record(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "available_rows": self.available_rows,
            "has_replay_date_row": self.has_replay_date_row,
            "is_missing_symbol": self.is_missing_symbol,
            "is_partial_warmup": self.is_partial_warmup,
        }


@dataclass(frozen=True)
class MarketDataDiagnostics:
    replay_date: date
    lookback_rows: int
    requested_symbols: tuple[str, ...]
    available_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    missing_replay_date_symbols: tuple[str, ...]
    partial_warmup_symbols: tuple[str, ...]
    symbols: tuple[MarketDataSymbolDiagnostic, ...]
    schema_version: str = MARKET_DATA_DIAGNOSTICS_SCHEMA_VERSION

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "lookback_rows": self.lookback_rows,
            "requested_symbols": list(self.requested_symbols),
            "available_symbols": list(self.available_symbols),
            "missing_symbols": list(self.missing_symbols),
            "missing_replay_date_symbols": list(self.missing_replay_date_symbols),
            "partial_warmup_symbols": list(self.partial_warmup_symbols),
            "symbols": [symbol.to_record() for symbol in self.symbols],
        }


def build_market_data_diagnostics(
    window: ReplayWarmupWindow,
) -> MarketDataDiagnostics:
    requested_symbols = window.requested_symbols or window.available_symbols
    rows_by_symbol = {
        symbol: tuple(row for row in window.rows if row.symbol == symbol)
        for symbol in requested_symbols
    }

    symbol_diagnostics: list[MarketDataSymbolDiagnostic] = []
    missing_replay_date_symbols: list[str] = []
    partial_warmup_symbols: list[str] = []

    for symbol in requested_symbols:
        symbol_rows = rows_by_symbol.get(symbol, ())
        available_rows = len(symbol_rows)
        has_replay_date_row = any(row.date == window.replay_date for row in symbol_rows)
        is_missing_symbol = symbol in window.missing_symbols
        is_partial_warmup = available_rows > 0 and available_rows < window.lookback_rows

        if not has_replay_date_row:
            missing_replay_date_symbols.append(symbol)
        if is_partial_warmup:
            partial_warmup_symbols.append(symbol)

        symbol_diagnostics.append(
            MarketDataSymbolDiagnostic(
                symbol=symbol,
                available_rows=available_rows,
                has_replay_date_row=has_replay_date_row,
                is_missing_symbol=is_missing_symbol,
                is_partial_warmup=is_partial_warmup,
            )
        )

    return MarketDataDiagnostics(
        replay_date=window.replay_date,
        lookback_rows=window.lookback_rows,
        requested_symbols=requested_symbols,
        available_symbols=window.available_symbols,
        missing_symbols=window.missing_symbols,
        missing_replay_date_symbols=tuple(missing_replay_date_symbols),
        partial_warmup_symbols=tuple(partial_warmup_symbols),
        symbols=tuple(symbol_diagnostics),
    )


def market_data_diagnostics_path(output_root: Path, replay_date: date) -> Path:
    return output_root / "market_data_diagnostics" / f"{replay_date.isoformat()}.json"


def write_market_data_diagnostics(
    path: Path,
    diagnostics: MarketDataDiagnostics,
) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
    ) as handle:
        json.dump(diagnostics.to_record(), handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    temp_path.replace(path)
    return path
