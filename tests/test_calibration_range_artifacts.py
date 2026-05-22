from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.check_output import build_fixture_check_replay_rows
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.range_artifacts import (
    RANGE_REPLAY_ARTIFACT_SCHEMA_VERSION,
    RANGE_REPLAY_MANIFEST_FILENAME,
    range_replay_output_dir,
    write_range_replay_artifacts,
)
from market_health.calibration.range_request import build_range_replay_request
from market_health.calibration.range_runner import run_range_replay


class RangeReplayArtifactsTest(unittest.TestCase):
    def test_writer_outputs_range_manifest_and_per_date_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "calibration"
            range_result = _range_result(tmp)
            check_rows_by_date = {
                replay_date: build_fixture_check_replay_rows(
                    replay_date=replay_date,
                    symbols=["SPY"],
                    horizons=["C"],
                )
                for replay_date in range_result.replay_dates
            }

            artifacts = write_range_replay_artifacts(
                output_root=output_root,
                range_result=range_result,
                check_rows_by_date=check_rows_by_date,
            )

            manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
            first_date_artifacts = artifacts.single_date_artifacts[0]
            with first_date_artifacts.check_rows_csv_path.open(
                newline="", encoding="utf-8"
            ) as handle:
                check_rows = list(csv.DictReader(handle))

        self.assertEqual(artifacts.schema_version, RANGE_REPLAY_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(artifacts.date_count, 2)
        self.assertEqual(artifacts.manifest_path.name, RANGE_REPLAY_MANIFEST_FILENAME)
        self.assertEqual(
            artifacts.output_dir.name,
            "2026-05-21_to_2026-05-22",
        )
        self.assertEqual(
            manifest["schema_version"], RANGE_REPLAY_ARTIFACT_SCHEMA_VERSION
        )
        self.assertEqual(manifest["range_replay"]["date_count"], 2)
        self.assertEqual(manifest["range_replay"]["total_row_count"], 2)
        self.assertEqual(manifest["artifacts"]["date_count"], 2)
        self.assertEqual(len(check_rows), 30)
        self.assertEqual(first_date_artifacts.output_dir.parent.name, "single_date")
        self.assertEqual(first_date_artifacts.output_dir.name, "2026-05-21")

    def test_range_output_dir_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "calibration"
            range_result = _range_result(tmp)

            self.assertEqual(
                range_replay_output_dir(output_root, range_result),
                output_root / "range_replay" / "2026-05-21_to_2026-05-22",
            )

    def test_default_check_rows_use_asof_eligible_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_range_replay_artifacts(
                output_root=Path(tmp) / "calibration",
                range_result=_range_result(tmp),
            )
            first_date_artifacts = artifacts.single_date_artifacts[0]

            with first_date_artifacts.check_rows_csv_path.open(
                newline="", encoding="utf-8"
            ) as handle:
                check_rows = list(csv.DictReader(handle))

        self.assertEqual(len(check_rows), 90)
        self.assertEqual({row["symbol"] for row in check_rows}, {"SPY"})

    def test_writer_rejects_live_runtime_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "live runtime state"):
                write_range_replay_artifacts(
                    output_root=Path(tmp) / ".cache" / "jerboa" / "runtime",
                    range_result=_range_result(tmp),
                )


def _range_result(tmp: str):
    request = build_range_replay_request(
        start_date=date(2026, 5, 21),
        end_date=date(2026, 5, 22),
        symbols=["SPY"],
        lookback_rows=2,
        output_root=Path(tmp) / "calibration",
    )
    return run_range_replay(
        request=request,
        price_rows=[
            _row("SPY", date(2026, 5, 21), 101.0),
            _row("SPY", date(2026, 5, 22), 102.0),
            _row("SPY", date(2026, 5, 23), 200.0),
        ],
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


if __name__ == "__main__":
    unittest.main()
