from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from market_health.calibration.check_output import (
    CHECK_REPLAY_ROW_COLUMNS,
    CheckReplayRow,
)
from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.export import (
    REPLAY_ROWS_TABLE,
    write_replay_rows_csv,
    write_replay_rows_sqlite,
)
from market_health.calibration.single_date_replay import SingleDateReplayResult

SINGLE_DATE_ARTIFACT_SCHEMA_VERSION = "calibration_single_date_artifacts.v1"
CHECK_REPLAY_ROWS_TABLE = "calibration_check_replay_rows"


@dataclass(frozen=True)
class SingleDateReplayArtifacts:
    output_dir: Path
    manifest_path: Path
    replay_rows_csv_path: Path
    replay_rows_sqlite_path: Path
    check_rows_csv_path: Path
    check_rows_sqlite_path: Path
    market_data_diagnostics_path: Path
    schema_version: str = SINGLE_DATE_ARTIFACT_SCHEMA_VERSION

    def to_record(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path),
            "replay_rows_csv_path": str(self.replay_rows_csv_path),
            "replay_rows_sqlite_path": str(self.replay_rows_sqlite_path),
            "check_rows_csv_path": str(self.check_rows_csv_path),
            "check_rows_sqlite_path": str(self.check_rows_sqlite_path),
            "market_data_diagnostics_path": str(self.market_data_diagnostics_path),
        }


def single_date_output_dir(
    output_root: Path, replay_result: SingleDateReplayResult
) -> Path:
    return output_root / "single_date" / replay_result.replay_date.isoformat()


def write_single_date_replay_artifacts(
    *,
    output_root: Path,
    replay_result: SingleDateReplayResult,
    check_rows: Iterable[CheckReplayRow],
) -> SingleDateReplayArtifacts:
    assert_not_live_runtime_path(output_root)

    output_dir = single_date_output_dir(output_root, replay_result)
    assert_not_live_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    check_row_tuple = tuple(check_rows)

    replay_rows_csv_path = write_replay_rows_csv(
        output_dir / "replay_rows.csv",
        replay_result.rows,
    )
    replay_rows_sqlite_path = write_replay_rows_sqlite(
        output_dir / "calibration.sqlite",
        replay_result.rows,
        table_name=REPLAY_ROWS_TABLE,
    )
    check_rows_csv_path = write_check_replay_rows_csv(
        output_dir / "check_replay_rows.csv",
        check_row_tuple,
    )
    check_rows_sqlite_path = write_check_replay_rows_sqlite(
        output_dir / "check_replay_rows.sqlite",
        check_row_tuple,
    )
    market_data_diagnostics_path = write_market_data_diagnostics_json(
        output_dir / "market_data_diagnostics.json",
        replay_result,
    )

    artifacts = SingleDateReplayArtifacts(
        output_dir=output_dir,
        manifest_path=output_dir / "manifest.json",
        replay_rows_csv_path=replay_rows_csv_path,
        replay_rows_sqlite_path=replay_rows_sqlite_path,
        check_rows_csv_path=check_rows_csv_path,
        check_rows_sqlite_path=check_rows_sqlite_path,
        market_data_diagnostics_path=market_data_diagnostics_path,
    )
    write_manifest_json(artifacts.manifest_path, replay_result, artifacts)
    return artifacts


def write_check_replay_rows_csv(
    path: Path,
    rows: Iterable[CheckReplayRow],
) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHECK_REPLAY_ROW_COLUMNS)
        writer.writeheader()
        writer.writerows(row.to_record() for row in rows)

    return path


def write_check_replay_rows_sqlite(
    path: Path,
    rows: Iterable[CheckReplayRow],
    *,
    table_name: str = CHECK_REPLAY_ROWS_TABLE,
) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        columns = ", ".join(f"{column} TEXT" for column in CHECK_REPLAY_ROW_COLUMNS)
        placeholders = ", ".join("?" for _ in CHECK_REPLAY_ROW_COLUMNS)
        column_names = ", ".join(CHECK_REPLAY_ROW_COLUMNS)

        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute(f"CREATE TABLE {table_name} ({columns})")
        conn.executemany(
            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",
            [
                tuple(
                    str(row.to_record()[column]) for column in CHECK_REPLAY_ROW_COLUMNS
                )
                for row in rows
            ],
        )
        conn.commit()

    return path


def write_market_data_diagnostics_json(
    path: Path,
    replay_result: SingleDateReplayResult,
) -> Path:
    diagnostics = replay_result.asof_input_record.get("market_data_diagnostics")
    if not isinstance(diagnostics, dict):
        raise ValueError("single-date replay result is missing market-data diagnostics")

    return _write_json(path, diagnostics)


def write_manifest_json(
    path: Path,
    replay_result: SingleDateReplayResult,
    artifacts: SingleDateReplayArtifacts,
) -> Path:
    payload = {
        "schema_version": SINGLE_DATE_ARTIFACT_SCHEMA_VERSION,
        "replay": replay_result.to_record(),
        "artifacts": artifacts.to_record(),
    }
    return _write_json(path, payload)


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    temp_path.replace(path)
    return path
