from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.range_request import build_range_replay_request
from market_health.calibration.range_runner import (
    RANGE_REPLAY_RESULT_SCHEMA_VERSION,
    RangeReplayResult,
    run_range_replay,
)


class RangeReplayRunnerTest(unittest.TestCase):
    def test_range_runner_builds_one_single_date_result_per_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_range_replay_request(
                start_date=date(2026, 5, 20),
                end_date=date(2026, 5, 22),
                symbols=["SPY"],
                lookback_rows=2,
                output_root=Path(tmp) / "calibration",
            )
            result = run_range_replay(
                request=request,
                price_rows=[
                    _row("SPY", date(2026, 5, 20), 100.0),
                    _row("SPY", date(2026, 5, 21), 101.0),
                    _row("SPY", date(2026, 5, 22), 102.0),
                    _row("SPY", date(2026, 5, 23), 200.0),
                ],
            )

        self.assertEqual(result.schema_version, RANGE_REPLAY_RESULT_SCHEMA_VERSION)
        self.assertEqual(result.date_count, 3)
        self.assertEqual(result.completed_date_count, 3)
        self.assertEqual(result.replay_dates, request.replay_dates)
        self.assertEqual([item.row_count for item in result.results], [1, 1, 1])
        self.assertEqual(result.total_row_count, 3)

    def test_range_runner_uses_asof_inputs_for_each_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_range_replay_request(
                start_date=date(2026, 5, 20),
                end_date=date(2026, 5, 22),
                symbols=["SPY"],
                lookback_rows=2,
                output_root=Path(tmp) / "calibration",
            )
            result = run_range_replay(
                request=request,
                price_rows=[
                    _row("SPY", date(2026, 5, 20), 100.0),
                    _row("SPY", date(2026, 5, 21), 101.0),
                    _row("SPY", date(2026, 5, 22), 102.0),
                    _row("SPY", date(2026, 5, 23), 200.0),
                ],
            )

        first = result.result_for_date(date(2026, 5, 20))
        last = result.result_for_date(date(2026, 5, 22))

        self.assertEqual(
            first.rows[0].audit_token, "single-date-asof:2026-05-20:SPY:1:100.0000"
        )
        self.assertEqual(
            last.rows[0].audit_token, "single-date-asof:2026-05-22:SPY:2:102.0000"
        )
        self.assertEqual(first.asof_input_record["excluded_future_row_count"], 3)
        self.assertEqual(last.asof_input_record["excluded_future_row_count"], 1)

    def test_range_result_record_has_stable_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_range_replay_request(
                start_date=date(2026, 5, 22),
                end_date=date(2026, 5, 22),
                symbols=["SPY"],
                lookback_rows=1,
                output_root=Path(tmp) / "calibration",
            )
            result = run_range_replay(
                request=request,
                price_rows=[_row("SPY", date(2026, 5, 22), 102.0)],
            )

        record = result.to_record()

        self.assertEqual(
            tuple(record),
            (
                "schema_version",
                "request",
                "date_count",
                "completed_date_count",
                "total_row_count",
                "replay_dates",
                "results",
            ),
        )
        self.assertEqual(record["schema_version"], RANGE_REPLAY_RESULT_SCHEMA_VERSION)
        self.assertEqual(record["replay_dates"], ["2026-05-22"])
        self.assertEqual(record["total_row_count"], 1)
        self.assertEqual(len(record["results"]), 1)

    def test_result_dates_must_match_request_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_range_replay_request(
                start_date=date(2026, 5, 20),
                end_date=date(2026, 5, 21),
                symbols=["SPY"],
                lookback_rows=1,
                output_root=Path(tmp) / "calibration",
            )
            source = run_range_replay(
                request=request,
                price_rows=[
                    _row("SPY", date(2026, 5, 20), 100.0),
                    _row("SPY", date(2026, 5, 21), 101.0),
                ],
            )

        with self.assertRaisesRegex(ValueError, "must match request replay dates"):
            RangeReplayResult(request=request, results=source.results[:1])

    def test_missing_replay_date_lookup_raises_key_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_range_replay_request(
                start_date=date(2026, 5, 22),
                end_date=date(2026, 5, 22),
                symbols=["SPY"],
                lookback_rows=1,
                output_root=Path(tmp) / "calibration",
            )
            result = run_range_replay(
                request=request,
                price_rows=[_row("SPY", date(2026, 5, 22), 102.0)],
            )

        with self.assertRaisesRegex(KeyError, "not found"):
            result.result_for_date(date(2026, 5, 23))


def _row(symbol: str, price_date: date, close: float) -> HistoricalPriceRow:
    return HistoricalPriceRow(
        symbol=symbol,
        date=price_date,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        adjusted_close=close,
        volume=1000,
    )


if __name__ == "__main__":
    unittest.main()
