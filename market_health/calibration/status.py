from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


STATUS_SCHEMA_VERSION = "calibration_replay_status.v1"
STATUS_FILENAME = "replay_status.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ReplayStatus:
    schema_version: str
    run_id: str
    started_at: str
    updated_at: str
    current_stage: str
    output_path: str
    total_dates: int = 0
    completed_dates: list[str] = field(default_factory=list)
    current_replay_date: str | None = None
    rows_written: int = 0
    latest_checkpoint: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, object]:
        return asdict(self)


def new_replay_status(
    *,
    run_id: str,
    output_path: Path,
    total_dates: int = 0,
    current_stage: str = "initialized",
) -> ReplayStatus:
    now = utc_now_iso()
    return ReplayStatus(
        schema_version=STATUS_SCHEMA_VERSION,
        run_id=run_id,
        started_at=now,
        updated_at=now,
        current_stage=current_stage,
        output_path=str(output_path),
        total_dates=total_dates,
    )


def status_path(output_root: Path) -> Path:
    return output_root / STATUS_FILENAME


def write_status(output_root: Path, status: ReplayStatus) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = status_path(output_root)
    payload = json.dumps(status.to_record(), indent=2, sort_keys=True) + "\n"

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_root,
        prefix=f".{STATUS_FILENAME}.",
        delete=False,
    ) as tmp:
        tmp.write(payload)
        temp_path = Path(tmp.name)

    temp_path.replace(path)
    return path


def read_status(output_root: Path) -> ReplayStatus:
    payload = json.loads(status_path(output_root).read_text(encoding="utf-8"))
    return ReplayStatus(**payload)


def mark_date_started(status: ReplayStatus, replay_date: date) -> ReplayStatus:
    return ReplayStatus(
        **{
            **status.to_record(),
            "updated_at": utc_now_iso(),
            "current_stage": "replaying_date",
            "current_replay_date": replay_date.isoformat(),
        }
    )


def mark_date_completed(
    status: ReplayStatus,
    replay_date: date,
    *,
    rows_written: int,
    checkpoint_path: Path | None = None,
) -> ReplayStatus:
    replay_date_text = replay_date.isoformat()
    completed_dates = list(status.completed_dates)
    if replay_date_text not in completed_dates:
        completed_dates.append(replay_date_text)

    return ReplayStatus(
        **{
            **status.to_record(),
            "updated_at": utc_now_iso(),
            "current_stage": "checkpointed",
            "current_replay_date": None,
            "completed_dates": completed_dates,
            "rows_written": status.rows_written + rows_written,
            "latest_checkpoint": str(checkpoint_path) if checkpoint_path else None,
        }
    )


def mark_failed(status: ReplayStatus, message: str) -> ReplayStatus:
    return ReplayStatus(
        **{
            **status.to_record(),
            "updated_at": utc_now_iso(),
            "current_stage": "failed",
            "errors": [*status.errors, message],
        }
    )
