from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from market_health.calibration.authoritative_dataset import (
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_MISSING,
    REALIZED_OUTCOME_NOT_APPLICABLE,
    REALIZED_OUTCOME_STATUSES,
)
from market_health.calibration.check_output import VALID_HORIZONS
from market_health.calibration.price_cache import HistoricalPriceRow

REALIZED_FORWARD_OUTCOME_SCHEMA_VERSION = "calibration_realized_forward_outcome.v1"

FORWARD_OUTCOME_HORIZON_OFFSETS = {
    "H1": 1,
    "H5": 5,
}

REALIZED_FORWARD_OUTCOME_COLUMNS = (
    "schema_version",
    "replay_date",
    "symbol",
    "horizon",
    "target_offset",
    "target_date",
    "origin_adjusted_close",
    "target_adjusted_close",
    "realized_return",
    "realized_current_score",
    "realized_outcome_status",
    "source_row_count",
)


@dataclass(frozen=True)
class RealizedForwardOutcome:
    replay_date: date
    symbol: str
    horizon: str
    realized_outcome_status: str
    target_offset: int | None = None
    target_date: date | None = None
    origin_adjusted_close: float | None = None
    target_adjusted_close: float | None = None
    realized_return: float | None = None
    realized_current_score: float | None = None
    source_row_count: int = 0
    schema_version: str = REALIZED_FORWARD_OUTCOME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REALIZED_FORWARD_OUTCOME_SCHEMA_VERSION:
            raise ValueError(
                "unsupported realized forward outcome schema version: "
                f"{self.schema_version}"
            )

        symbol = self.symbol.strip().upper()
        horizon = self.horizon.strip().upper()

        if not symbol:
            raise ValueError("realized forward outcome symbol is required")
        if horizon not in VALID_HORIZONS:
            raise ValueError(
                f"unsupported realized forward outcome horizon: {self.horizon}"
            )
        if self.realized_outcome_status not in REALIZED_OUTCOME_STATUSES:
            raise ValueError(
                f"unsupported realized outcome status: {self.realized_outcome_status}"
            )
        if self.source_row_count < 0:
            raise ValueError(
                "realized forward outcome source_row_count must be non-negative"
            )

        if self.realized_outcome_status == REALIZED_OUTCOME_AVAILABLE:
            for field_name in (
                "target_offset",
                "target_date",
                "origin_adjusted_close",
                "target_adjusted_close",
                "realized_return",
                "realized_current_score",
            ):
                if getattr(self, field_name) is None:
                    raise ValueError(
                        f"available realized outcome requires {field_name}"
                    )

        if self.realized_outcome_status == REALIZED_OUTCOME_NOT_APPLICABLE:
            for field_name in (
                "target_offset",
                "target_date",
                "origin_adjusted_close",
                "target_adjusted_close",
                "realized_return",
                "realized_current_score",
            ):
                if getattr(self, field_name) is not None:
                    raise ValueError(
                        f"not_applicable realized outcome cannot set {field_name}"
                    )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "horizon", horizon)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "symbol": self.symbol,
            "horizon": self.horizon,
            "target_offset": self.target_offset,
            "target_date": _optional_date(self.target_date),
            "origin_adjusted_close": self.origin_adjusted_close,
            "target_adjusted_close": self.target_adjusted_close,
            "realized_return": self.realized_return,
            "realized_current_score": self.realized_current_score,
            "realized_outcome_status": self.realized_outcome_status,
            "source_row_count": self.source_row_count,
        }


def resolve_realized_forward_outcome(
    rows: Iterable[HistoricalPriceRow],
    *,
    replay_date: date,
    symbol: str,
    horizon: str,
) -> RealizedForwardOutcome:
    source_rows = tuple(rows)
    normalized_symbol = symbol.strip().upper()
    normalized_horizon = horizon.strip().upper()

    if normalized_horizon == "C":
        return RealizedForwardOutcome(
            replay_date=replay_date,
            symbol=normalized_symbol,
            horizon=normalized_horizon,
            realized_outcome_status=REALIZED_OUTCOME_NOT_APPLICABLE,
            source_row_count=_source_row_count(source_rows, normalized_symbol),
        )

    if normalized_horizon not in FORWARD_OUTCOME_HORIZON_OFFSETS:
        raise ValueError(f"unsupported forward outcome horizon: {horizon}")

    target_offset = FORWARD_OUTCOME_HORIZON_OFFSETS[normalized_horizon]
    symbol_rows = tuple(
        sorted(
            (row for row in source_rows if row.symbol == normalized_symbol),
            key=lambda row: row.date,
        )
    )
    origin_row = _row_for_date(symbol_rows, replay_date)
    future_rows = tuple(row for row in symbol_rows if row.date > replay_date)

    if origin_row is None or len(future_rows) < target_offset:
        return RealizedForwardOutcome(
            replay_date=replay_date,
            symbol=normalized_symbol,
            horizon=normalized_horizon,
            target_offset=target_offset,
            target_date=_available_target_date(future_rows, target_offset),
            realized_outcome_status=REALIZED_OUTCOME_MISSING,
            source_row_count=len(symbol_rows),
        )

    target_row = future_rows[target_offset - 1]
    realized_return = _realized_return(
        origin_row.adjusted_close,
        target_row.adjusted_close,
    )

    return RealizedForwardOutcome(
        replay_date=replay_date,
        symbol=normalized_symbol,
        horizon=normalized_horizon,
        target_offset=target_offset,
        target_date=target_row.date,
        origin_adjusted_close=origin_row.adjusted_close,
        target_adjusted_close=target_row.adjusted_close,
        realized_return=realized_return,
        realized_current_score=_realized_current_score(realized_return),
        realized_outcome_status=REALIZED_OUTCOME_AVAILABLE,
        source_row_count=len(symbol_rows),
    )


def resolve_realized_forward_outcomes(
    rows: Iterable[HistoricalPriceRow],
    *,
    replay_date: date,
    symbols: Iterable[str],
    horizons: Iterable[str] = VALID_HORIZONS,
) -> tuple[RealizedForwardOutcome, ...]:
    source_rows = tuple(rows)
    outcomes = []
    for symbol in _normalize_symbols(symbols):
        for horizon in _normalize_horizons(horizons):
            outcomes.append(
                resolve_realized_forward_outcome(
                    source_rows,
                    replay_date=replay_date,
                    symbol=symbol,
                    horizon=horizon,
                )
            )

    return tuple(sorted(outcomes, key=lambda item: (item.symbol, item.horizon)))


def _row_for_date(
    rows: tuple[HistoricalPriceRow, ...],
    target_date: date,
) -> HistoricalPriceRow | None:
    for row in rows:
        if row.date == target_date:
            return row
    return None


def _available_target_date(
    future_rows: tuple[HistoricalPriceRow, ...],
    target_offset: int,
) -> date | None:
    if len(future_rows) < target_offset:
        return None
    return future_rows[target_offset - 1].date


def _realized_return(
    origin_adjusted_close: float,
    target_adjusted_close: float,
) -> float:
    if origin_adjusted_close <= 0:
        return 0.0
    return round(
        (target_adjusted_close - origin_adjusted_close) / origin_adjusted_close,
        8,
    )


def _realized_current_score(realized_return: float) -> float:
    return round(max(0.0, min(10.0, 5.0 + realized_return * 100.0)), 4)


def _source_row_count(rows: tuple[HistoricalPriceRow, ...], symbol: str) -> int:
    return sum(row.symbol == symbol for row in rows)


def _optional_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


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


def _normalize_horizons(horizons: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for horizon in horizons:
        value = horizon.strip().upper()
        if value not in VALID_HORIZONS:
            raise ValueError(f"unsupported realized outcome horizon: {horizon}")
        if value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return tuple(normalized)
