from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.asof_inputs import build_asof_input_bundle
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.range_failure_accounting import (
    RANGE_REPLAY_ACCOUNTING_SCHEMA_VERSION,
    RangeReplayDateFailure,
    run_range_replay_with_failure_accounting,
)
from market_health.calibration.range_progress import (
    mark_range_date_completed,
    mark_range_date_failed,
    new_range_replay_progress,
)
from market_health.calibration.range_request import (
    RangeReplayRequest,
    build_range_replay_request,
)
from market_health.calibration.single_date_replay import (
    SingleDateReplayResult,
    build_single_date_replay_rows,
)


class RangeReplayFailureAccountingTest(unittest.TestCase):
    def test_successful_range_replay_accounting_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            result = run_range_replay_with_failure_accounting(
                request=request,
                price_rows=_price_rows(),
                run_id="run-1",
            )

        self.assertEqual(result.schema_version, RANGE_REPLAY_ACCOUNTING_SCHEMA_VERSION)
        self.assertEqual(result.date_count, 3)
        self.assertEqual(result.completed_date_count, 3)
        self.assertEqual(result.failed_date_count, 0)
        self.assertEqual(result.pending_date_count, 0)
        self.assertEqual(result.skipped_date_count, 0)
        self.assertEqual(result.attempted_date_count, 3)
        self.assertEqual(result.rows_written, 3)
        self.assertEqual(
            result.progress.completed_dates,
            ("2026-05-20", "2026-05-21", "2026-05-22"),
        )

    def test_date_failure_is_recorded_and_later_dates_continue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            result = run_range_replay_with_failure_accounting(
                request=request,
                price_rows=_price_rows(),
                run_id="run-1",
                date_replay_function=_fail_on_2026_05_21,
            )

        self.assertEqual(result.completed_date_count, 2)
        self.assertEqual(result.failed_date_count, 1)
        self.assertEqual(result.pending_date_count, 0)
        self.assertEqual(result.attempted_date_count, 3)
        self.assertEqual(result.rows_written, 2)
        self.assertEqual(
            [item.replay_date for item in result.results],
            [date(2026, 5, 20), date(2026, 5, 22)],
        )
        self.assertEqual(
            result.failures[0].to_record(),
            {"replay_date": "2026-05-21", "message": "fixture failure"},
        )
        self.assertIn("2026-05-21: fixture failure", result.progress.errors)

    def test_fail_fast_records_failure_and_leaves_later_date_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            result = run_range_replay_with_failure_accounting(
                request=request,
                price_rows=_price_rows(),
                run_id="run-1",
                date_replay_function=_fail_on_2026_05_21,
                fail_fast=True,
            )

        self.assertEqual(result.completed_date_count, 1)
        self.assertEqual(result.failed_date_count, 1)
        self.assertEqual(result.pending_date_count, 1)
        self.assertEqual(result.attempted_date_count, 2)
        self.assertEqual(result.rows_written, 1)
        self.assertEqual(
            [item.replay_date for item in result.results], [date(2026, 5, 20)]
        )
        self.assertEqual(result.failures[0].replay_date, date(2026, 5, 21))

    def test_resume_skips_previously_completed_and_failed_dates(self) -> None:
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
                message="previous failure",
            )

            result = run_range_replay_with_failure_accounting(
                request=request,
                price_rows=_price_rows(),
                progress=progress,
            )

        self.assertEqual(result.skipped_dates, (date(2026, 5, 20), date(2026, 5, 21)))
        self.assertEqual(result.skipped_date_count, 2)
        self.assertEqual(result.attempted_date_count, 1)
        self.assertEqual(result.completed_date_count, 2)
        self.assertEqual(result.failed_date_count, 1)
        self.assertEqual(result.pending_date_count, 0)
        self.assertEqual(result.rows_written, 2)
        self.assertEqual(
            [item.replay_date for item in result.results], [date(2026, 5, 22)]
        )

    def test_accounting_record_has_stable_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(tmp)
            result = run_range_replay_with_failure_accounting(
                request=request,
                price_rows=_price_rows(),
                run_id="run-1",
                date_replay_function=_fail_on_2026_05_21,
            )

        record = result.to_record()

        self.assertEqual(
            tuple(record),
            (
                "schema_version",
                "request",
                "progress",
                "date_count",
                "completed_date_count",
                "failed_date_count",
                "pending_date_count",
                "skipped_date_count",
                "attempted_date_count",
                "rows_written",
                "skipped_dates",
                "failures",
                "results",
            ),
        )
        self.assertEqual(record["failed_date_count"], 1)
        self.assertEqual(
            record["failures"],
            [{"replay_date": "2026-05-21", "message": "fixture failure"}],
        )

    def test_empty_failure_message_uses_exception_class_name(self) -> None:
        failure = RangeReplayDateFailure(
            replay_date=date(2026, 5, 21), message="RuntimeError"
        )
        self.assertEqual(
            failure.to_record(),
            {"replay_date": "2026-05-21", "message": "RuntimeError"},
        )


def _request(tmp: str):
    return build_range_replay_request(
        start_date=date(2026, 5, 20),
        end_date=date(2026, 5, 22),
        symbols=["SPY"],
        lookback_rows=2,
        output_root=Path(tmp) / "calibration",
    )


def _price_rows() -> tuple[HistoricalPriceRow, ...]:
    return (
        _row("SPY", date(2026, 5, 20), 100.0),
        _row("SPY", date(2026, 5, 21), 101.0),
        _row("SPY", date(2026, 5, 22), 102.0),
    )


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


def _fail_on_2026_05_21(
    request: RangeReplayRequest,
    replay_date: date,
    price_rows: tuple[HistoricalPriceRow, ...],
    engine_metadata,
) -> SingleDateReplayResult:
    if replay_date == date(2026, 5, 21):
        raise RuntimeError("fixture failure")

    bundle = build_asof_input_bundle(
        replay_date=replay_date,
        symbols=request.symbols,
        price_rows=price_rows,
        lookback_rows=request.lookback_rows,
    )
    return build_single_date_replay_rows(
        bundle,
        engine_metadata=engine_metadata,
    )


if __name__ == "__main__":
    unittest.main()
