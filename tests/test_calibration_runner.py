from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.runner import (
    fixture_rows_for_date,
    run_fixture_replay,
)


class CalibrationRunnerTest(unittest.TestCase):
    def test_fixture_rows_for_date_are_deterministic(self) -> None:
        rows = fixture_rows_for_date(date(2026, 5, 22), ["SPY", "QQQ"])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].symbol, "SPY")
        self.assertEqual(rows[0].current_score, 8.0)
        self.assertEqual(rows[0].h1_score, 8.5)
        self.assertEqual(rows[0].h5_score, 7.5)
        self.assertEqual(rows[0].state, "GREEN")
        self.assertEqual(rows[1].symbol, "QQQ")
        self.assertEqual(rows[1].state, "YELLOW")

    def test_run_fixture_replay_writes_status_and_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "calibration"
            result = run_fixture_replay(
                output_root=output_root,
                replay_dates=[date(2026, 5, 21), date(2026, 5, 22)],
                symbols=["SPY", "QQQ"],
                run_id="test-run",
            )

            status_payload = json.loads(
                (output_root / "replay_status.json").read_text(encoding="utf-8")
            )
            with result.csv_path.open(encoding="utf-8", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            with sqlite3.connect(result.sqlite_path) as conn:
                sqlite_count = conn.execute(
                    "SELECT COUNT(*) FROM calibration_replay_rows"
                ).fetchone()[0]

        self.assertEqual(len(result.rows), 4)
        self.assertEqual(result.status.completed_dates, ["2026-05-21", "2026-05-22"])
        self.assertEqual(result.status.rows_written, 4)
        self.assertEqual(status_payload["run_id"], "test-run")
        self.assertEqual(status_payload["current_stage"], "checkpointed")
        self.assertEqual(len(csv_rows), 4)
        self.assertEqual(sqlite_count, 4)
        self.assertEqual(
            result.engine_metadata["schema_version"], "calibration_engine_metadata.v1"
        )

    def test_run_fixture_replay_rejects_live_runtime_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / ".cache" / "jerboa" / "positions.v1.json"
            with self.assertRaises(ValueError):
                run_fixture_replay(
                    output_root=output_root,
                    replay_dates=[date(2026, 5, 22)],
                    symbols=["SPY"],
                )


if __name__ == "__main__":
    unittest.main()
