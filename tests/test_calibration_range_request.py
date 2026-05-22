from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.range_request import (
    RANGE_REPLAY_REQUEST_COLUMNS,
    RANGE_REPLAY_REQUEST_SCHEMA_VERSION,
    RangeReplayRequest,
    build_range_replay_request,
    iter_replay_dates,
    normalize_range_symbols,
)


class RangeReplayRequestTest(unittest.TestCase):
    def test_request_record_has_stable_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_range_replay_request(
                start_date=date(2026, 5, 20),
                end_date=date(2026, 5, 22),
                symbols=["spy", "QQQ", "spy", ""],
                lookback_rows=5,
                output_root=Path(tmp) / "calibration",
            )

        record = request.to_record()

        self.assertEqual(tuple(record), RANGE_REPLAY_REQUEST_COLUMNS)
        self.assertEqual(record["schema_version"], RANGE_REPLAY_REQUEST_SCHEMA_VERSION)
        self.assertEqual(record["start_date"], "2026-05-20")
        self.assertEqual(record["end_date"], "2026-05-22")
        self.assertEqual(record["date_count"], 3)
        self.assertEqual(record["symbols"], ["SPY", "QQQ"])
        self.assertEqual(record["lookback_rows"], 5)

    def test_iter_replay_dates_is_inclusive_and_deterministic(self) -> None:
        self.assertEqual(
            tuple(iter_replay_dates(date(2026, 5, 20), date(2026, 5, 22))),
            (
                date(2026, 5, 20),
                date(2026, 5, 21),
                date(2026, 5, 22),
            ),
        )

    def test_single_day_range_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_range_replay_request(
                start_date=date(2026, 5, 22),
                end_date=date(2026, 5, 22),
                symbols=["SPY"],
                lookback_rows=1,
                output_root=Path(tmp) / "calibration",
            )

        self.assertEqual(request.replay_dates, (date(2026, 5, 22),))
        self.assertEqual(request.date_count, 1)

    def test_symbol_normalization_deduplicates_and_omits_blanks(self) -> None:
        self.assertEqual(
            normalize_range_symbols([" spy ", "QQQ", "spy", "", " qqq "]),
            ("SPY", "QQQ"),
        )

    def test_invalid_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "start date"):
            tuple(iter_replay_dates(date(2026, 5, 23), date(2026, 5, 22)))

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "start date"):
                build_range_replay_request(
                    start_date=date(2026, 5, 23),
                    end_date=date(2026, 5, 22),
                    symbols=["SPY"],
                    lookback_rows=1,
                    output_root=Path(tmp) / "calibration",
                )

    def test_empty_symbols_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "at least one symbol"):
                build_range_replay_request(
                    start_date=date(2026, 5, 22),
                    end_date=date(2026, 5, 22),
                    symbols=["", "  "],
                    lookback_rows=1,
                    output_root=Path(tmp) / "calibration",
                )

    def test_non_positive_lookback_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "lookback_rows"):
                build_range_replay_request(
                    start_date=date(2026, 5, 22),
                    end_date=date(2026, 5, 22),
                    symbols=["SPY"],
                    lookback_rows=0,
                    output_root=Path(tmp) / "calibration",
                )

    def test_live_runtime_output_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "live runtime state"):
                RangeReplayRequest(
                    start_date=date(2026, 5, 22),
                    end_date=date(2026, 5, 22),
                    symbols=("SPY",),
                    lookback_rows=1,
                    output_root=Path(tmp) / ".cache" / "jerboa" / "runtime",
                )


if __name__ == "__main__":
    unittest.main()
