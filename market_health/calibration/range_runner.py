from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from market_health.calibration.asof_inputs import build_asof_input_bundle
from market_health.calibration.engine_metadata import EngineMetadata
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.range_request import RangeReplayRequest
from market_health.calibration.single_date_replay import (
    SingleDateReplayResult,
    build_single_date_replay_rows,
)

RANGE_REPLAY_RESULT_SCHEMA_VERSION = "calibration_range_replay_result.v1"


@dataclass(frozen=True)
class RangeReplayResult:
    request: RangeReplayRequest
    results: tuple[SingleDateReplayResult, ...]
    schema_version: str = RANGE_REPLAY_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RANGE_REPLAY_RESULT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported range replay result schema version: {self.schema_version}"
            )

        result_dates = tuple(result.replay_date for result in self.results)
        if result_dates != self.request.replay_dates:
            raise ValueError("range replay results must match request replay dates")

    @property
    def date_count(self) -> int:
        return self.request.date_count

    @property
    def completed_date_count(self) -> int:
        return len(self.results)

    @property
    def total_row_count(self) -> int:
        return sum(result.row_count for result in self.results)

    @property
    def replay_dates(self) -> tuple[date, ...]:
        return tuple(result.replay_date for result in self.results)

    def result_for_date(self, replay_date: date) -> SingleDateReplayResult:
        for result in self.results:
            if result.replay_date == replay_date:
                return result
        raise KeyError(f"range replay result not found for date: {replay_date}")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.to_record(),
            "date_count": self.date_count,
            "completed_date_count": self.completed_date_count,
            "total_row_count": self.total_row_count,
            "replay_dates": [item.isoformat() for item in self.replay_dates],
            "results": [result.to_record() for result in self.results],
        }


def run_range_replay(
    *,
    request: RangeReplayRequest,
    price_rows: Iterable[HistoricalPriceRow],
    engine_metadata: EngineMetadata | None = None,
) -> RangeReplayResult:
    source_rows = tuple(price_rows)
    results = []

    for replay_date in request.replay_dates:
        bundle = build_asof_input_bundle(
            replay_date=replay_date,
            symbols=request.symbols,
            price_rows=source_rows,
            lookback_rows=request.lookback_rows,
        )
        results.append(
            build_single_date_replay_rows(
                bundle,
                engine_metadata=engine_metadata,
            )
        )

    return RangeReplayResult(
        request=request,
        results=tuple(results),
    )
