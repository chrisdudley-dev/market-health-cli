from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.export import (
    REPLAY_ROW_COLUMNS,
    REPLAY_ROWS_TABLE,
    replay_rows_to_records,
    write_replay_rows_csv,
    write_replay_rows_sqlite,
)
from market_health.calibration.schema import (
    REPLAY_ARTIFACT_SCHEMA_VERSION,
    ReplayArtifactRow,
)


def sample_rows() -> list[ReplayArtifactRow]:
    return [
        ReplayArtifactRow(
            replay_date=date(2026, 5, 20),
            symbol="SPY",
            current_score=8.0,
            h1_score=8.5,
            h5_score=7.5,
            blend_score=8.1,
            state="GREEN",
            audit_token="A=888:111111",
        ),
        ReplayArtifactRow(
            replay_date=date(2026, 5, 21),
            symbol="QQQ",
            current_score=7.0,
            h1_score=7.5,
            h5_score=6.5,
            blend_score=7.1,
            state="YELLOW",
            audit_token=None,
        ),
    ]


class CalibrationExportTest(unittest.TestCase):
    def test_replay_rows_to_records(self) -> None:
        records = replay_rows_to_records(sample_rows())

        self.assertEqual(len(records), 2)
        self.assertEqual(set(records[0]), set(REPLAY_ROW_COLUMNS))
        self.assertEqual(
            records[0]["schema_version"],
            REPLAY_ARTIFACT_SCHEMA_VERSION,
        )
        self.assertEqual(records[0]["replay_date"], "2026-05-20")
        self.assertEqual(records[0]["symbol"], "SPY")

    def test_write_replay_rows_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reports" / "replay_rows.csv"
            written = write_replay_rows_csv(path, sample_rows())

            with written.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(written.name, "replay_rows.csv")
        self.assertEqual(list(rows[0].keys()), list(REPLAY_ROW_COLUMNS))
        self.assertEqual(rows[0]["schema_version"], REPLAY_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(rows[0]["replay_date"], "2026-05-20")
        self.assertEqual(rows[0]["symbol"], "SPY")
        self.assertEqual(rows[1]["audit_token"], "")

    def test_write_replay_rows_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reports" / "calibration.sqlite"
            written = write_replay_rows_sqlite(path, sample_rows())

            with sqlite3.connect(written) as conn:
                table_count = conn.execute(
                    "SELECT COUNT(*) FROM calibration_replay_rows"
                ).fetchone()[0]
                first_row = conn.execute(
                    """
                    SELECT
                        schema_version,
                        replay_date,
                        symbol,
                        current_score,
                        h1_score,
                        h5_score,
                        blend_score,
                        state,
                        audit_token
                    FROM calibration_replay_rows
                    ORDER BY replay_date, symbol
                    LIMIT 1
                    """
                ).fetchone()

        self.assertEqual(written.name, "calibration.sqlite")
        self.assertEqual(table_count, 2)
        self.assertEqual(first_row[0], REPLAY_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(first_row[1], "2026-05-20")
        self.assertEqual(first_row[2], "SPY")
        self.assertEqual(first_row[3], 8.0)
        self.assertEqual(first_row[8], "A=888:111111")

    def test_sqlite_table_name_constant(self) -> None:
        self.assertEqual(REPLAY_ROWS_TABLE, "calibration_replay_rows")


if __name__ == "__main__":
    unittest.main()
