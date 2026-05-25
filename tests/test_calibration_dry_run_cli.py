from __future__ import annotations

import csv
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from market_health.calibration.calibration_adjustment_export import (
    CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE,
    CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE,
    CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE,
)
from market_health.calibration.cli import build_parser, main
from market_health.calibration.price_cache import HISTORICAL_PRICE_CACHE_COLUMNS


class CalibrationDryRunCliTest(unittest.TestCase):
    def test_calibration_dry_run_help_is_registered(self) -> None:
        parser = build_parser()

        self.assertIn("calibration-dry-run", parser.format_help())

    def test_calibration_dry_run_command_writes_artifacts_and_outputs_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            price_cache_path = tmp_path / "prices.csv"
            output_root = tmp_path / "calibration"
            _write_price_cache(price_cache_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "calibration-dry-run",
                        "--price-cache",
                        str(price_cache_path),
                        "--start-date",
                        "2026-05-20",
                        "--end-date",
                        "2026-05-20",
                        "--symbols",
                        "SPY",
                        "--lookback-rows",
                        "1",
                        "--out",
                        str(output_root),
                        "--dataset-run-id",
                        "dataset-test",
                        "--residual-attribution-run-id",
                        "residual-test",
                        "--calibration-review-run-id",
                        "review-test",
                        "--dry-run-simulation-run-id",
                        "dry-run-test",
                        "--review-min-observation-count",
                        "1",
                        "--adjustment-min-observation-count",
                        "1",
                        "--max-examples-per-group",
                        "1",
                        "--window-days",
                        "1",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            artifacts = payload["artifacts"]
            candidates_csv_path = Path(artifacts["candidates_csv_path"])
            simulation_rows_csv_path = Path(artifacts["simulation_rows_csv_path"])
            comparison_rows_csv_path = Path(artifacts["comparison_rows_csv_path"])
            sqlite_path = Path(artifacts["sqlite_path"])
            validation_summary_path = Path(artifacts["validation_summary_path"])
            manifest_path = Path(artifacts["manifest_path"])

            with candidates_csv_path.open(newline="", encoding="utf-8") as handle:
                candidate_rows = list(csv.DictReader(handle))
            with simulation_rows_csv_path.open(newline="", encoding="utf-8") as handle:
                simulation_rows = list(csv.DictReader(handle))
            with comparison_rows_csv_path.open(newline="", encoding="utf-8") as handle:
                comparison_rows = list(csv.DictReader(handle))

            with sqlite3.connect(sqlite_path) as connection:
                sqlite_candidate_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE}"
                ).fetchone()[0]
                sqlite_simulation_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE}"
                ).fetchone()[0]
                sqlite_comparison_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE}"
                ).fetchone()[0]

            validation_summary = json.loads(
                validation_summary_path.read_text(encoding="utf-8")
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["command"], "calibration-dry-run")
        self.assertEqual(payload["dataset_run_id"], "dataset-test")
        self.assertEqual(payload["residual_attribution_run_id"], "residual-test")
        self.assertEqual(payload["calibration_review_run_id"], "review-test")
        self.assertEqual(payload["dry_run_simulation_run_id"], "dry-run-test")
        self.assertEqual(payload["dataset_row_count"], 90)
        self.assertEqual(payload["residual_observation_count"], 60)
        self.assertGreater(payload["candidate_count"], 0)
        self.assertGreater(payload["simulation_row_count"], 0)
        self.assertGreater(payload["comparison_row_count"], 0)

        self.assertEqual(len(candidate_rows), payload["candidate_count"])
        self.assertEqual(len(simulation_rows), payload["simulation_row_count"])
        self.assertEqual(len(comparison_rows), payload["comparison_row_count"])
        self.assertEqual(sqlite_candidate_count, payload["candidate_count"])
        self.assertEqual(sqlite_simulation_count, payload["simulation_row_count"])
        self.assertEqual(sqlite_comparison_count, payload["comparison_row_count"])
        self.assertEqual(
            validation_summary["candidate_count"], payload["candidate_count"]
        )
        self.assertEqual(
            validation_summary["dry_run_simulation_run_ids"],
            ["dry-run-test"],
        )
        self.assertEqual(manifest["candidate_count"], payload["candidate_count"])
        self.assertEqual(
            manifest["simulation_row_count"], payload["simulation_row_count"]
        )

    def test_calibration_dry_run_rejects_bad_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            price_cache_path = Path(tmp) / "prices.csv"
            _write_price_cache(price_cache_path)

            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "calibration-dry-run",
                        "--price-cache",
                        str(price_cache_path),
                        "--start-date",
                        "2026/05/20",
                        "--end-date",
                        "2026-05-20",
                        "--symbols",
                        "SPY",
                    ]
                )

        self.assertEqual(raised.exception.code, 2)


def _write_price_cache(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        _price_row(date(2026, 5, 20), 100.0),
        _price_row(date(2026, 5, 21), 103.0),
        _price_row(date(2026, 5, 22), 104.0),
        _price_row(date(2026, 5, 26), 106.0),
        _price_row(date(2026, 5, 27), 108.0),
        _price_row(date(2026, 5, 28), 110.0),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORICAL_PRICE_CACHE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _price_row(price_date: date, close: float) -> dict[str, str]:
    return {
        "schema_version": "historical_price_cache.v1",
        "source": "fixture",
        "symbol": "SPY",
        "date": price_date.isoformat(),
        "open": str(close - 1.0),
        "high": str(close + 1.0),
        "low": str(close - 2.0),
        "close": str(close),
        "adjusted_close": str(close),
        "volume": "1000",
    }


if __name__ == "__main__":
    unittest.main()
