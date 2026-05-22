from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.engine_metadata import capture_engine_metadata
from market_health.calibration.export import (
    write_replay_rows_csv,
    write_replay_rows_sqlite,
)
from market_health.calibration.schema import ReplayArtifactRow
from market_health.calibration.status import (
    ReplayStatus,
    mark_date_completed,
    mark_date_started,
    new_replay_status,
    write_status,
)


@dataclass(frozen=True)
class ReplayRunResult:
    output_root: Path
    rows: list[ReplayArtifactRow]
    status: ReplayStatus
    csv_path: Path
    sqlite_path: Path
    engine_metadata: dict[str, object]


def fixture_rows_for_date(
    replay_date: date, symbols: list[str]
) -> list[ReplayArtifactRow]:
    rows: list[ReplayArtifactRow] = []
    for index, symbol in enumerate(symbols):
        current_score = 8.0 - index
        h1_score = current_score + 0.5
        h5_score = current_score - 0.5
        rows.append(
            ReplayArtifactRow(
                replay_date=replay_date,
                symbol=symbol,
                current_score=current_score,
                h1_score=h1_score,
                h5_score=h5_score,
                blend_score=current_score + 0.1,
                state="GREEN" if current_score >= 8.0 else "YELLOW",
                audit_token=None,
            )
        )
    return rows


def run_fixture_replay(
    *,
    output_root: Path,
    replay_dates: list[date],
    symbols: list[str],
    run_id: str = "fixture-run",
) -> ReplayRunResult:
    """Run a deterministic fixture replay through the artifact pipeline."""
    assert_not_live_runtime_path(output_root)

    status = new_replay_status(
        run_id=run_id,
        output_path=output_root,
        total_dates=len(replay_dates),
    )
    write_status(output_root, status)

    rows: list[ReplayArtifactRow] = []
    for replay_date in replay_dates:
        status = mark_date_started(status, replay_date)
        write_status(output_root, status)

        date_rows = fixture_rows_for_date(replay_date, symbols)
        rows.extend(date_rows)

        checkpoint_path = (
            output_root / "checkpoints" / f"{replay_date.isoformat()}.json"
        )
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            "\n".join(row.symbol for row in date_rows) + "\n",
            encoding="utf-8",
        )

        status = mark_date_completed(
            status,
            replay_date,
            rows_written=len(date_rows),
            checkpoint_path=checkpoint_path,
        )
        write_status(output_root, status)

    csv_path = write_replay_rows_csv(output_root / "replay_rows.csv", rows)
    sqlite_path = write_replay_rows_sqlite(output_root / "calibration.sqlite", rows)
    engine_metadata = capture_engine_metadata()

    return ReplayRunResult(
        output_root=output_root,
        rows=rows,
        status=status,
        csv_path=csv_path,
        sqlite_path=sqlite_path,
        engine_metadata=engine_metadata,
    )
