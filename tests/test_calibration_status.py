from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.status import (
    STATUS_FILENAME,
    STATUS_SCHEMA_VERSION,
    mark_date_completed,
    mark_date_started,
    mark_failed,
    new_replay_status,
    read_status,
    status_path,
    write_status,
)


class ReplayStatusTest(unittest.TestCase):
    def test_new_status_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            status = new_replay_status(
                run_id="run-001",
                output_path=output_root,
                total_dates=3,
            )

        self.assertEqual(status.schema_version, STATUS_SCHEMA_VERSION)
        self.assertEqual(status.run_id, "run-001")
        self.assertEqual(status.current_stage, "initialized")
        self.assertEqual(status.total_dates, 3)
        self.assertEqual(status.completed_dates, [])
        self.assertEqual(status.rows_written, 0)
        self.assertEqual(status.errors, [])

    def test_status_path_uses_stable_filename(self) -> None:
        self.assertEqual(
            status_path(Path("/tmp/out")), Path("/tmp/out") / STATUS_FILENAME
        )

    def test_write_and_read_status_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            status = new_replay_status(run_id="run-002", output_path=output_root)

            written = write_status(output_root, status)
            loaded = read_status(output_root)

        self.assertEqual(written.name, STATUS_FILENAME)
        self.assertEqual(loaded, status)

    def test_written_status_is_pretty_sorted_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            status = new_replay_status(run_id="run-003", output_path=output_root)

            written = write_status(output_root, status)
            payload = json.loads(written.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], STATUS_SCHEMA_VERSION)
        self.assertEqual(payload["run_id"], "run-003")

    def test_mark_date_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = new_replay_status(run_id="run-004", output_path=Path(tmp))
            updated = mark_date_started(status, date(2026, 5, 22))

        self.assertEqual(updated.current_stage, "replaying_date")
        self.assertEqual(updated.current_replay_date, "2026-05-22")
        self.assertEqual(updated.completed_dates, [])

    def test_mark_date_completed_is_idempotent_for_completed_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = new_replay_status(
                run_id="run-005",
                output_path=Path(tmp),
                total_dates=1,
            )
            started = mark_date_started(status, date(2026, 5, 22))
            completed_once = mark_date_completed(
                started,
                date(2026, 5, 22),
                rows_written=10,
                checkpoint_path=Path(tmp) / "checkpoint-001.json",
            )
            completed_twice = mark_date_completed(
                completed_once,
                date(2026, 5, 22),
                rows_written=5,
                checkpoint_path=Path(tmp) / "checkpoint-001.json",
            )

        self.assertEqual(completed_once.current_stage, "checkpointed")
        self.assertIsNone(completed_once.current_replay_date)
        self.assertEqual(completed_once.completed_dates, ["2026-05-22"])
        self.assertEqual(completed_once.rows_written, 10)
        self.assertEqual(completed_twice.completed_dates, ["2026-05-22"])
        self.assertEqual(completed_twice.rows_written, 15)

    def test_mark_failed_appends_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = new_replay_status(run_id="run-006", output_path=Path(tmp))
            failed = mark_failed(status, "fixture data unavailable")

        self.assertEqual(failed.current_stage, "failed")
        self.assertEqual(failed.errors, ["fixture data unavailable"])


if __name__ == "__main__":
    unittest.main()
