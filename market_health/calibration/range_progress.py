from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.range_request import RangeReplayRequest
from market_health.calibration.status import utc_now_iso

RANGE_REPLAY_PROGRESS_SCHEMA_VERSION = "calibration_range_replay_progress.v1"
RANGE_REPLAY_PROGRESS_FILENAME = "range_replay_progress.json"


@dataclass(frozen=True)
class RangeReplayProgress:
    schema_version: str
    run_id: str
    started_at: str
    updated_at: str
    request_record: dict[str, object]
    total_dates: int
    completed_dates: tuple[str, ...] = field(default_factory=tuple)
    failed_dates: tuple[str, ...] = field(default_factory=tuple)
    current_replay_date: str | None = None
    rows_written: int = 0
    latest_checkpoint: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.schema_version != RANGE_REPLAY_PROGRESS_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported range replay progress schema version: {self.schema_version}"
            )
        if self.total_dates < 0:
            raise ValueError("range replay progress total_dates cannot be negative")
        if self.rows_written < 0:
            raise ValueError("range replay progress rows_written cannot be negative")

        object.__setattr__(self, "completed_dates", tuple(self.completed_dates))
        object.__setattr__(self, "failed_dates", tuple(self.failed_dates))
        object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def completed_date_count(self) -> int:
        return len(self.completed_dates)

    @property
    def failed_date_count(self) -> int:
        return len(self.failed_dates)

    @property
    def pending_date_count(self) -> int:
        return max(
            0,
            self.total_dates - self.completed_date_count - self.failed_date_count,
        )

    def to_record(self) -> dict[str, object]:
        record = asdict(self)
        record["completed_dates"] = list(self.completed_dates)
        record["failed_dates"] = list(self.failed_dates)
        record["errors"] = list(self.errors)
        record["completed_date_count"] = self.completed_date_count
        record["failed_date_count"] = self.failed_date_count
        record["pending_date_count"] = self.pending_date_count
        return record


def new_range_replay_progress(
    *,
    request: RangeReplayRequest,
    run_id: str,
) -> RangeReplayProgress:
    now = utc_now_iso()
    return RangeReplayProgress(
        schema_version=RANGE_REPLAY_PROGRESS_SCHEMA_VERSION,
        run_id=run_id,
        started_at=now,
        updated_at=now,
        request_record=request.to_record(),
        total_dates=request.date_count,
    )


def pending_replay_dates(
    request: RangeReplayRequest,
    progress: RangeReplayProgress,
) -> tuple[date, ...]:
    completed = set(progress.completed_dates)
    failed = set(progress.failed_dates)
    return tuple(
        replay_date
        for replay_date in request.replay_dates
        if replay_date.isoformat() not in completed
        and replay_date.isoformat() not in failed
    )


def next_replay_date(
    request: RangeReplayRequest,
    progress: RangeReplayProgress,
) -> date | None:
    pending = pending_replay_dates(request, progress)
    return pending[0] if pending else None


def should_skip_replay_date(progress: RangeReplayProgress, replay_date: date) -> bool:
    replay_date_text = replay_date.isoformat()
    return (
        replay_date_text in progress.completed_dates
        or replay_date_text in progress.failed_dates
    )


def mark_range_date_started(
    progress: RangeReplayProgress,
    replay_date: date,
) -> RangeReplayProgress:
    return _replace_progress(
        progress,
        updated_at=utc_now_iso(),
        current_replay_date=replay_date.isoformat(),
    )


def mark_range_date_completed(
    progress: RangeReplayProgress,
    replay_date: date,
    *,
    rows_written: int,
    checkpoint_path: Path | None = None,
) -> RangeReplayProgress:
    replay_date_text = replay_date.isoformat()
    completed_dates = _append_unique(progress.completed_dates, replay_date_text)
    failed_dates = tuple(
        item for item in progress.failed_dates if item != replay_date_text
    )

    return _replace_progress(
        progress,
        updated_at=utc_now_iso(),
        completed_dates=completed_dates,
        failed_dates=failed_dates,
        current_replay_date=None,
        rows_written=progress.rows_written + rows_written,
        latest_checkpoint=str(checkpoint_path)
        if checkpoint_path
        else progress.latest_checkpoint,
    )


def mark_range_date_failed(
    progress: RangeReplayProgress,
    replay_date: date,
    *,
    message: str,
) -> RangeReplayProgress:
    replay_date_text = replay_date.isoformat()
    failed_dates = _append_unique(progress.failed_dates, replay_date_text)

    return _replace_progress(
        progress,
        updated_at=utc_now_iso(),
        failed_dates=failed_dates,
        current_replay_date=None,
        errors=(*progress.errors, f"{replay_date_text}: {message}"),
    )


def range_progress_path(output_root: Path) -> Path:
    return output_root / RANGE_REPLAY_PROGRESS_FILENAME


def write_range_progress(output_root: Path, progress: RangeReplayProgress) -> Path:
    assert_not_live_runtime_path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    path = range_progress_path(output_root)
    payload = json.dumps(progress.to_record(), indent=2, sort_keys=True) + "\n"

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_root,
        prefix=f".{RANGE_REPLAY_PROGRESS_FILENAME}.",
        delete=False,
    ) as tmp:
        tmp.write(payload)
        temp_path = Path(tmp.name)

    temp_path.replace(path)
    return path


def read_range_progress(output_root: Path) -> RangeReplayProgress:
    assert_not_live_runtime_path(output_root)
    payload = json.loads(range_progress_path(output_root).read_text(encoding="utf-8"))
    return RangeReplayProgress(
        schema_version=payload["schema_version"],
        run_id=payload["run_id"],
        started_at=payload["started_at"],
        updated_at=payload["updated_at"],
        request_record=payload["request_record"],
        total_dates=payload["total_dates"],
        completed_dates=tuple(payload.get("completed_dates", ())),
        failed_dates=tuple(payload.get("failed_dates", ())),
        current_replay_date=payload.get("current_replay_date"),
        rows_written=payload.get("rows_written", 0),
        latest_checkpoint=payload.get("latest_checkpoint"),
        errors=tuple(payload.get("errors", ())),
    )


def _replace_progress(
    progress: RangeReplayProgress,
    **updates: object,
) -> RangeReplayProgress:
    record = {
        "schema_version": progress.schema_version,
        "run_id": progress.run_id,
        "started_at": progress.started_at,
        "updated_at": progress.updated_at,
        "request_record": progress.request_record,
        "total_dates": progress.total_dates,
        "completed_dates": progress.completed_dates,
        "failed_dates": progress.failed_dates,
        "current_replay_date": progress.current_replay_date,
        "rows_written": progress.rows_written,
        "latest_checkpoint": progress.latest_checkpoint,
        "errors": progress.errors,
    }
    record.update(updates)
    return RangeReplayProgress(**record)


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    if value in values:
        return values
    return (*values, value)
