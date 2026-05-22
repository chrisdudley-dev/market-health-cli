from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable

from market_health.calibration.asof_inputs import build_asof_input_bundle
from market_health.calibration.engine_metadata import EngineMetadata
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.range_progress import (
    RangeReplayProgress,
    mark_range_date_completed,
    mark_range_date_failed,
    mark_range_date_started,
    new_range_replay_progress,
    pending_replay_dates,
    should_skip_replay_date,
)
from market_health.calibration.range_request import RangeReplayRequest
from market_health.calibration.single_date_replay import (
    SingleDateReplayResult,
    build_single_date_replay_rows,
)

RANGE_REPLAY_ACCOUNTING_SCHEMA_VERSION = "calibration_range_replay_accounting.v1"

DateReplayFunction = Callable[
    [RangeReplayRequest, date, tuple[HistoricalPriceRow, ...], EngineMetadata | None],
    SingleDateReplayResult,
]


@dataclass(frozen=True)
class RangeReplayDateFailure:
    replay_date: date
    message: str

    def to_record(self) -> dict[str, str]:
        return {
            "replay_date": self.replay_date.isoformat(),
            "message": self.message,
        }


@dataclass(frozen=True)
class RangeReplayAccountingResult:
    request: RangeReplayRequest
    progress: RangeReplayProgress
    results: tuple[SingleDateReplayResult, ...]
    failures: tuple[RangeReplayDateFailure, ...]
    skipped_dates: tuple[date, ...]
    schema_version: str = RANGE_REPLAY_ACCOUNTING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RANGE_REPLAY_ACCOUNTING_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported range replay accounting schema version: {self.schema_version}"
            )
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "skipped_dates", tuple(self.skipped_dates))

    @property
    def date_count(self) -> int:
        return self.request.date_count

    @property
    def completed_date_count(self) -> int:
        return self.progress.completed_date_count

    @property
    def failed_date_count(self) -> int:
        return self.progress.failed_date_count

    @property
    def pending_date_count(self) -> int:
        return self.progress.pending_date_count

    @property
    def skipped_date_count(self) -> int:
        return len(self.skipped_dates)

    @property
    def attempted_date_count(self) -> int:
        return len(self.results) + len(self.failures)

    @property
    def rows_written(self) -> int:
        return self.progress.rows_written

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.to_record(),
            "progress": self.progress.to_record(),
            "date_count": self.date_count,
            "completed_date_count": self.completed_date_count,
            "failed_date_count": self.failed_date_count,
            "pending_date_count": self.pending_date_count,
            "skipped_date_count": self.skipped_date_count,
            "attempted_date_count": self.attempted_date_count,
            "rows_written": self.rows_written,
            "skipped_dates": [item.isoformat() for item in self.skipped_dates],
            "failures": [failure.to_record() for failure in self.failures],
            "results": [result.to_record() for result in self.results],
        }


def run_range_replay_with_failure_accounting(
    *,
    request: RangeReplayRequest,
    price_rows: Iterable[HistoricalPriceRow],
    run_id: str = "range-replay",
    progress: RangeReplayProgress | None = None,
    engine_metadata: EngineMetadata | None = None,
    date_replay_function: DateReplayFunction | None = None,
    fail_fast: bool = False,
) -> RangeReplayAccountingResult:
    source_rows = tuple(price_rows)
    working_progress = progress or new_range_replay_progress(
        request=request,
        run_id=run_id,
    )
    skipped_dates = tuple(
        replay_date
        for replay_date in request.replay_dates
        if should_skip_replay_date(working_progress, replay_date)
    )
    replay_one_date = date_replay_function or _default_date_replay_function

    results: list[SingleDateReplayResult] = []
    failures: list[RangeReplayDateFailure] = []

    for replay_date in pending_replay_dates(request, working_progress):
        working_progress = mark_range_date_started(working_progress, replay_date)

        try:
            result = replay_one_date(
                request,
                replay_date,
                source_rows,
                engine_metadata,
            )
        except Exception as exc:
            message = _failure_message(exc)
            failures.append(
                RangeReplayDateFailure(
                    replay_date=replay_date,
                    message=message,
                )
            )
            working_progress = mark_range_date_failed(
                working_progress,
                replay_date,
                message=message,
            )
            if fail_fast:
                break
            continue

        results.append(result)
        working_progress = mark_range_date_completed(
            working_progress,
            replay_date,
            rows_written=result.row_count,
        )

    return RangeReplayAccountingResult(
        request=request,
        progress=working_progress,
        results=tuple(results),
        failures=tuple(failures),
        skipped_dates=skipped_dates,
    )


def _default_date_replay_function(
    request: RangeReplayRequest,
    replay_date: date,
    price_rows: tuple[HistoricalPriceRow, ...],
    engine_metadata: EngineMetadata | None,
) -> SingleDateReplayResult:
    bundle = build_asof_input_bundle(
        replay_date=replay_date,
        symbols=request.symbols,
        price_rows=price_rows,
        lookback_rows=request.lookback_rows,
    )
    return build_single_date_replay_rows(
        bundle,
        engine_metadata=engine_metadata,
    )


def _failure_message(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__
