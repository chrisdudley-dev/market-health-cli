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

from market_health.calibration.cli import build_parser, main
from market_health.calibration.price_cache import HISTORICAL_PRICE_CACHE_COLUMNS
from market_health.calibration.residual_attribution_export import (
    RESIDUAL_ATTRIBUTION_ROWS_TABLE,
    RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE,
)


class ResidualAttributionCliTest(unittest.TestCase):
    def test_residual_attribution_help_is_registered(self) -> None:
        parser = build_parser()
        self.assertIn("residual-attribution", parser.format_help())

    def test_residual_attribution_command_writes_artifacts_and_outputs_json(
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
                        "residual-attribution",
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
                    ]
                )

            payload = json.loads(stdout.getvalue())
            artifacts = payload["artifacts"]
            rows_csv_path = Path(artifacts["rows_csv_path"])
            summaries_csv_path = Path(artifacts["summaries_csv_path"])
            sqlite_path = Path(artifacts["sqlite_path"])
            validation_summary_path = Path(artifacts["validation_summary_path"])
            manifest_path = Path(artifacts["manifest_path"])

            with rows_csv_path.open(newline="", encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
            with summaries_csv_path.open(newline="", encoding="utf-8") as handle:
                summary_rows = list(csv.DictReader(handle))

            with sqlite3.connect(sqlite_path) as conn:
                sqlite_row_count = conn.execute(
                    f"SELECT COUNT(*) FROM {RESIDUAL_ATTRIBUTION_ROWS_TABLE}"
                ).fetchone()[0]
                sqlite_summary_count = conn.execute(
                    f"SELECT COUNT(*) FROM {RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE}"
                ).fetchone()[0]

            validation_summary = json.loads(
                validation_summary_path.read_text(encoding="utf-8")
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["command"], "residual-attribution")
        self.assertEqual(payload["dataset_run_id"], "dataset-test")
        self.assertEqual(payload["residual_attribution_run_id"], "residual-test")
        self.assertEqual(payload["dataset_row_count"], 90)
        self.assertEqual(payload["observation_count"], 60)
        self.assertGreater(payload["summary_count"], 0)
        self.assertEqual(len(csv_rows), payload["observation_count"])
        self.assertEqual(len(summary_rows), payload["summary_count"])
        self.assertEqual(sqlite_row_count, payload["observation_count"])
        self.assertEqual(sqlite_summary_count, payload["summary_count"])
        self.assertEqual(validation_summary["observation_count"], 60)
        self.assertEqual(
            validation_summary["residual_attribution_run_ids"], ["residual-test"]
        )
        self.assertEqual(validation_summary["dataset_run_ids"], ["dataset-test"])
        self.assertEqual(manifest["observation_count"], 60)
        self.assertEqual(manifest["summary_count"], payload["summary_count"])

    def test_residual_attribution_rejects_bad_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            price_cache_path = Path(tmp) / "prices.csv"
            _write_price_cache(price_cache_path)

            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "residual-attribution",
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
