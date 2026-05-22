from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from market_health.calibration.schema import ReplayArtifactRow


REPLAY_ROWS_TABLE = "calibration_replay_rows"

REPLAY_ROW_COLUMNS = (
    "schema_version",
    "replay_date",
    "symbol",
    "current_score",
    "h1_score",
    "h5_score",
    "blend_score",
    "state",
    "audit_token",
)


def replay_rows_to_records(
    rows: Iterable[ReplayArtifactRow],
) -> list[dict[str, object]]:
    return [row.to_record() for row in rows]


def write_replay_rows_csv(path: Path, rows: Iterable[ReplayArtifactRow]) -> Path:
    records = replay_rows_to_records(rows)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPLAY_ROW_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    return path


def write_replay_rows_sqlite(
    path: Path,
    rows: Iterable[ReplayArtifactRow],
    *,
    table_name: str = REPLAY_ROWS_TABLE,
) -> Path:
    records = replay_rows_to_records(rows)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute(
            f"""
            CREATE TABLE {table_name} (
                schema_version TEXT NOT NULL,
                replay_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                current_score REAL NOT NULL,
                h1_score REAL NOT NULL,
                h5_score REAL NOT NULL,
                blend_score REAL NOT NULL,
                state TEXT NOT NULL,
                audit_token TEXT
            )
            """
        )
        conn.executemany(
            f"""
            INSERT INTO {table_name} (
                schema_version,
                replay_date,
                symbol,
                current_score,
                h1_score,
                h5_score,
                blend_score,
                state,
                audit_token
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                tuple(record[column] for column in REPLAY_ROW_COLUMNS)
                for record in records
            ],
        )

    return path
