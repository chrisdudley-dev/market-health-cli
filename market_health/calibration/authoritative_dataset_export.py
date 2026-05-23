from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable

from market_health.calibration.authoritative_dataset import (
    AUTHORITATIVE_REPLAY_DATASET_COLUMNS,
    AuthoritativeReplayDatasetRow,
)
from market_health.calibration.defaults import assert_not_live_runtime_path

AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE = (
    "calibration_authoritative_replay_dataset_rows"
)


def authoritative_dataset_rows_to_records(
    rows: Iterable[AuthoritativeReplayDatasetRow],
) -> list[dict[str, object]]:
    return [
        row.to_record()
        for row in sorted(tuple(rows), key=_authoritative_dataset_row_key)
    ]


def write_authoritative_dataset_rows_csv(
    path: Path,
    rows: Iterable[AuthoritativeReplayDatasetRow],
) -> Path:
    assert_not_live_runtime_path(path)
    records = authoritative_dataset_rows_to_records(rows)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=AUTHORITATIVE_REPLAY_DATASET_COLUMNS,
        )
        writer.writeheader()
        writer.writerows(records)

    return path


def write_authoritative_dataset_rows_sqlite(
    path: Path,
    rows: Iterable[AuthoritativeReplayDatasetRow],
    *,
    table_name: str = AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE,
) -> Path:
    assert_not_live_runtime_path(path)
    records = authoritative_dataset_rows_to_records(rows)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        columns = ", ".join(
            f"{column} {sqlite_type_for_authoritative_dataset_column(column)}"
            for column in AUTHORITATIVE_REPLAY_DATASET_COLUMNS
        )
        placeholders = ", ".join("?" for _ in AUTHORITATIVE_REPLAY_DATASET_COLUMNS)
        column_names = ", ".join(AUTHORITATIVE_REPLAY_DATASET_COLUMNS)

        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute(f"CREATE TABLE {table_name} ({columns})")
        conn.executemany(
            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",
            [
                tuple(record[column] for column in AUTHORITATIVE_REPLAY_DATASET_COLUMNS)
                for record in records
            ],
        )
        conn.commit()

    return path


def sqlite_type_for_authoritative_dataset_column(column: str) -> str:
    if column in {
        "current_score",
        "h1_score",
        "h5_score",
        "blend_score",
        "realized_current_score",
        "realized_return",
        "check_score",
    }:
        return "REAL"
    if column == "slot":
        return "INTEGER"
    return "TEXT"


def _authoritative_dataset_row_key(
    row: AuthoritativeReplayDatasetRow,
) -> tuple[str, str, str, int, str]:
    return (
        row.replay_date.isoformat(),
        row.symbol,
        row.category,
        row.slot,
        row.horizon,
    )
