from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.range_progress import (
    RANGE_REPLAY_PROGRESS_FILENAME,
    RANGE_REPLAY_PROGRESS_SCHEMA_VERSION,
    mark_range_date_completed,
    mark_range_date_failed,
    mark_range_date_started,
    new_range_replay_progress,
    next_replay_date,
    pending_replay_dates,
    range_progress_path,
    read_range_progress,
    should_skip_replay_date,
    write_range_progress,
)
from market_health.calibration.range_request import build_range_replay_request


class RangeReplayProgressTest(unittest.TestCase):
    def test_new_progress_record_has_stable_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            progress = new_range_replay_progress(request=request, run_id="run-1")

        record = progress.to_record()

        self.assertEqual(record["schema_version"], RANGE_REPLAY_PROGRESS_SCHEMA_VERSION)
        self.assertEqual(record["run_id"], "run-1")
        self.assertEqual(record["total_dates"], 3)
        self.assertEqual(record["completed_dates"], [])
        self.assertEqual(record["failed_dates"], [])
        self.assertEqual(record["completed_date_count"], 0)
        self.assertEqual(record["failed_date_count"], 0)
        self.assertEqual(record["pending_date_count"], 3)
        self.assertEqual(record["request_record"]["start_date"], "2026-05-20")

    def test_started_and_completed_dates_update_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            progress = new_range_replay_progress(request=request, run_id="run-1")

        progress = mark_range_date_started(progress, date(2026, 5, 20))
        self.assertEqual(progress.current_replay_date, "2026-05-20")

        progress = mark_range_date_completed(
            progress,
            date(2026, 5, 20),
            rows_written=2,
            checkpoint_path=Path("checkpoint.json"),
        )

        self.assertEqual(progress.completed_dates, ("2026-05-20",))
        self.assertEqual(progress.current_replay_date, None)
        self.assertEqual(progress.rows_written, 2)
        self.assertEqual(progress.latest_checkpoint, "checkpoint.json")
        self.assertEqual(progress.pending_date_count, 2)

    def test_completion_is_idempotent_for_dates_but_not_row_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            progress = new_range_replay_progress(request=request, run_id="run-1")

        progress = mark_range_date_completed(
            progress,
            date(2026, 5, 20),
            rows_written=2,
        )
        progress = mark_range_date_completed(
            progress,
            date(2026, 5, 20),
            rows_written=0,
        )

        self.assertEqual(progress.completed_dates, ("2026-05-20",))
        self.assertEqual(progress.rows_written, 2)

    def test_failed_dates_are_tracked_for_resume_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            progress = new_range_replay_progress(request=request, run_id="run-1")

        progress = mark_range_date_failed(
            progress,
            date(2026, 5, 21),
            message="fixture failure",
        )

        self.assertEqual(progress.failed_dates, ("2026-05-21",))
        self.assertEqual(progress.failed_date_count, 1)
        self.assertEqual(progress.pending_date_count, 2)
        self.assertIn("2026-05-21: fixture failure", progress.errors)
        self.assertTrue(should_skip_replay_date(progress, date(2026, 5, 21)))

    def test_pending_dates_skip_completed_and_failed_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            progress = new_range_replay_progress(request=request, run_id="run-1")

        progress = mark_range_date_completed(
            progress,
            date(2026, 5, 20),
            rows_written=1,
        )
        progress = mark_range_date_failed(
            progress,
            date(2026, 5, 21),
            message="boom",
        )

        self.assertEqual(pending_replay_dates(request, progress), (date(2026, 5, 22),))
        self.assertEqual(next_replay_date(request, progress), date(2026, 5, 22))
        self.assertTrue(should_skip_replay_date(progress, date(2026, 5, 20)))
        self.assertFalse(should_skip_replay_date(progress, date(2026, 5, 22)))

    def test_write_and_read_progress_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "calibration"
            request = _request(tmp)
            progress = new_range_replay_progress(request=request, run_id="run-1")
            progress = mark_range_date_completed(
                progress,
                date(2026, 5, 20),
                rows_written=3,
            )

            path = write_range_progress(output_root, progress)
            loaded = read_range_progress(output_root)

        self.assertEqual(path.name, RANGE_REPLAY_PROGRESS_FILENAME)
        self.assertEqual(
            range_progress_path(output_root).name, RANGE_REPLAY_PROGRESS_FILENAME
        )
        self.assertEqual(loaded.run_id, progress.run_id)
        self.assertEqual(loaded.completed_dates, ("2026-05-20",))
        self.assertEqual(loaded.rows_written, 3)

    def test_live_runtime_output_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            progress = new_range_replay_progress(request=request, run_id="run-1")
            output_root = Path(tmp) / ".cache" / "jerboa" / "runtime"

            with self.assertRaisesRegex(ValueError, "live runtime state"):
                write_range_progress(output_root, progress)


def _request(tmp: str):
    return build_range_replay_request(
        start_date=date(2026, 5, 20),
        end_date=date(2026, 5, 22),
        symbols=["SPY"],
        lookback_rows=2,
        output_root=Path(tmp) / "calibration",
    )


if __name__ == "__main__":
    unittest.main()
