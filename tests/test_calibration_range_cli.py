from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from market_health.calibration import cli
from market_health.calibration.price_cache import (
    HISTORICAL_PRICE_CACHE_COLUMNS,
    HistoricalPriceRow,
)
from market_health.calibration.range_progress import read_range_progress


class RangeReplayCliTest(unittest.TestCase):
    def test_range_replay_command_writes_progress_and_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "calibration"
            price_cache_path = Path(tmp) / "prices.csv"
            _write_price_cache(
                price_cache_path,
                [
                    _row("SPY", date(2026, 5, 20), 100.0),
                    _row("SPY", date(2026, 5, 21), 101.0),
                    _row("SPY", date(2026, 5, 22), 102.0),
                ],
            )

            payload = _run_cli_json(
                [
                    "range-replay",
                    "--price-cache",
                    str(price_cache_path),
                    "--start-date",
                    "2026-05-20",
                    "--end-date",
                    "2026-05-22",
                    "--symbols",
                    "spy",
                    "--lookback-rows",
                    "2",
                    "--out",
                    str(output_root),
                    "--run-id",
                    "cli-test",
                ]
            )
            progress = read_range_progress(output_root)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["command"], "range-replay")
        self.assertEqual(payload["result"]["completed_date_count"], 3)
        self.assertEqual(payload["result"]["failed_date_count"], 0)
        self.assertEqual(payload["result"]["rows_written"], 3)
        self.assertEqual(progress.run_id, "cli-test")
        self.assertEqual(
            progress.completed_dates,
            ("2026-05-20", "2026-05-21", "2026-05-22"),
        )

    def test_range_replay_resume_skips_completed_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "calibration"
            price_cache_path = Path(tmp) / "prices.csv"
            _write_price_cache(
                price_cache_path,
                [
                    _row("SPY", date(2026, 5, 20), 100.0),
                    _row("SPY", date(2026, 5, 21), 101.0),
                ],
            )

            base_args = [
                "range-replay",
                "--price-cache",
                str(price_cache_path),
                "--start-date",
                "2026-05-20",
                "--end-date",
                "2026-05-21",
                "--symbols",
                "SPY",
                "--lookback-rows",
                "1",
                "--out",
                str(output_root),
                "--run-id",
                "cli-test",
            ]
            _run_cli_json(base_args)
            resumed = _run_cli_json([*base_args, "--resume"])
            progress = read_range_progress(output_root)

        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(resumed["result"]["skipped_date_count"], 2)
        self.assertEqual(resumed["result"]["attempted_date_count"], 0)
        self.assertEqual(resumed["result"]["rows_written"], 2)
        self.assertEqual(progress.completed_dates, ("2026-05-20", "2026-05-21"))

    def test_range_replay_rejects_bad_date(self) -> None:
        with self.assertRaises(SystemExit):
            cli.main(
                [
                    "range-replay",
                    "--price-cache",
                    "prices.csv",
                    "--start-date",
                    "2026/05/20",
                    "--end-date",
                    "2026-05-21",
                    "--symbols",
                    "SPY",
                ]
            )

    def test_range_replay_help_is_registered(self) -> None:
        parser = cli.build_parser()
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stdout(io.StringIO()) as stdout:
                parser.parse_args(["range-replay", "--help"])

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("--price-cache", stdout.getvalue())
        self.assertIn("--resume", stdout.getvalue())


def _run_cli_json(argv: list[str]) -> dict[str, object]:
    stream = io.StringIO()
    with redirect_stdout(stream):
        status = cli.main(argv)

    if status != 0:
        raise AssertionError(f"unexpected CLI status: {status}")

    return json.loads(stream.getvalue())


def _write_price_cache(path: Path, rows: list[HistoricalPriceRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORICAL_PRICE_CACHE_COLUMNS)
        writer.writeheader()
        writer.writerows(row.to_record() for row in rows)


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
