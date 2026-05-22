from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from typing import Any

from market_health.calibration.asof_inputs import AsOfInputBundle
from market_health.calibration.engine_metadata import (
    EngineMetadata,
    capture_engine_metadata,
)
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.schema import ReplayArtifactRow

SINGLE_DATE_REPLAY_SCHEMA_VERSION = "calibration_single_date_replay.v1"


@dataclass(frozen=True)
class SingleDateReplayResult:
    replay_date: date
    rows: tuple[ReplayArtifactRow, ...]
    engine_metadata: EngineMetadata
    asof_input_record: dict[str, object]
    schema_version: str = SINGLE_DATE_REPLAY_SCHEMA_VERSION

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "row_count": self.row_count,
            "engine_metadata": _metadata_to_record(self.engine_metadata),
            "asof_input": self.asof_input_record,
            "rows": [row.to_record() for row in self.rows],
        }


def build_single_date_replay_rows(
    bundle: AsOfInputBundle,
    *,
    engine_metadata: EngineMetadata | None = None,
) -> SingleDateReplayResult:
    metadata = engine_metadata or capture_engine_metadata()
    rows_by_symbol = _rows_by_symbol(bundle.price_rows)

    replay_rows = []
    for symbol in bundle.eligible_symbols:
        symbol_rows = rows_by_symbol.get(symbol, ())
        if not any(row.date == bundle.replay_date for row in symbol_rows):
            continue
        replay_rows.append(
            _build_replay_artifact_row(
                replay_date=bundle.replay_date,
                symbol=symbol,
                rows=symbol_rows,
            )
        )

    return SingleDateReplayResult(
        replay_date=bundle.replay_date,
        rows=tuple(sorted(replay_rows, key=lambda row: row.symbol)),
        engine_metadata=metadata,
        asof_input_record=bundle.to_record(),
    )


def _build_replay_artifact_row(
    *,
    replay_date: date,
    symbol: str,
    rows: tuple[HistoricalPriceRow, ...],
) -> ReplayArtifactRow:
    ordered_rows = tuple(sorted(rows, key=lambda row: row.date))
    first = ordered_rows[0].adjusted_close
    last = ordered_rows[-1].adjusted_close
    row_count = len(ordered_rows)

    if first <= 0:
        current_score = 5.0
        slope_score = 0.0
    else:
        total_return = (last - first) / first
        current_score = _clamp_score(5.0 + total_return * 100.0)
        slope = 0.0 if row_count <= 1 else (last - first) / (row_count - 1)
        slope_score = (slope / first) * 100.0

    h1_score = _clamp_score(current_score + slope_score)
    h5_score = _clamp_score(current_score + slope_score * 2.0)
    blend_score = round((current_score + h1_score + h5_score) / 3.0, 4)

    return ReplayArtifactRow(
        replay_date=replay_date,
        symbol=symbol,
        current_score=current_score,
        h1_score=h1_score,
        h5_score=h5_score,
        blend_score=blend_score,
        state=_state_for_blend(blend_score),
        audit_token=(
            f"single-date-asof:{replay_date.isoformat()}:{symbol}:"
            f"{row_count}:{last:.4f}"
        ),
    )


def _rows_by_symbol(
    rows: tuple[HistoricalPriceRow, ...],
) -> dict[str, tuple[HistoricalPriceRow, ...]]:
    grouped: dict[str, list[HistoricalPriceRow]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)

    return {
        symbol: tuple(sorted(symbol_rows, key=lambda row: row.date))
        for symbol, symbol_rows in grouped.items()
    }


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 4)


def _state_for_blend(blend_score: float) -> str:
    if blend_score >= 7.0:
        return "GREEN"
    if blend_score >= 4.0:
        return "YELLOW"
    return "RED"


def _metadata_to_record(metadata: EngineMetadata) -> dict[str, Any]:
    to_record = getattr(metadata, "to_record", None)
    if callable(to_record):
        return dict(to_record())
    if is_dataclass(metadata):
        return asdict(metadata)
    return {"repr": repr(metadata)}
