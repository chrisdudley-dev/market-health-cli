from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from market_health.calibration.defaults import assert_not_live_runtime_path

RANGE_REPLAY_REQUEST_SCHEMA_VERSION = "calibration_range_replay_request.v1"

RANGE_REPLAY_REQUEST_COLUMNS = (
    "schema_version",
    "start_date",
    "end_date",
    "date_count",
    "symbols",
    "lookback_rows",
    "output_root",
)


@dataclass(frozen=True)
class RangeReplayRequest:
    start_date: date
    end_date: date
    symbols: tuple[str, ...]
    lookback_rows: int
    output_root: Path
    schema_version: str = RANGE_REPLAY_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RANGE_REPLAY_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported range replay request schema version: {self.schema_version}"
            )
        if self.start_date > self.end_date:
            raise ValueError("range replay start date must be on or before end date")
        if self.lookback_rows <= 0:
            raise ValueError("range replay lookback_rows must be positive")

        normalized_symbols = normalize_range_symbols(self.symbols)
        if not normalized_symbols:
            raise ValueError("range replay request requires at least one symbol")

        output_root = Path(self.output_root)
        assert_not_live_runtime_path(output_root)

        object.__setattr__(self, "symbols", normalized_symbols)
        object.__setattr__(self, "output_root", output_root)

    @property
    def replay_dates(self) -> tuple[date, ...]:
        return tuple(iter_replay_dates(self.start_date, self.end_date))

    @property
    def date_count(self) -> int:
        return len(self.replay_dates)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "date_count": self.date_count,
            "symbols": list(self.symbols),
            "lookback_rows": self.lookback_rows,
            "output_root": str(self.output_root),
        }


def build_range_replay_request(
    *,
    start_date: date,
    end_date: date,
    symbols: Iterable[str],
    lookback_rows: int,
    output_root: Path,
) -> RangeReplayRequest:
    return RangeReplayRequest(
        start_date=start_date,
        end_date=end_date,
        symbols=normalize_range_symbols(symbols),
        lookback_rows=lookback_rows,
        output_root=output_root,
    )


def iter_replay_dates(start_date: date, end_date: date) -> Iterable[date]:
    if start_date > end_date:
        raise ValueError("range replay start date must be on or before end date")

    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def normalize_range_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()

    for symbol in symbols:
        value = symbol.strip().upper()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)

    return tuple(normalized)
