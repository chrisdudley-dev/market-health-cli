from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.asof_inputs import build_asof_input_bundle
from market_health.calibration.check_output import build_fixture_check_replay_rows
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.single_date_artifacts import (
    CHECK_REPLAY_ROWS_TABLE,
    SINGLE_DATE_ARTIFACT_SCHEMA_VERSION,
    write_single_date_replay_artifacts,
)
from market_health.calibration.single_date_replay import build_single_date_replay_rows


class SingleDateReplayArtifactsTest(unittest.TestCase):
    def test_writer_outputs_replay_check_diagnostics_and_manifest(self) -> None:
        bundle = build_asof_input_bundle(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            price_rows=[
                _row("SPY", date(2026, 5, 21), 100.0),
                _row("SPY", date(2026, 5, 22), 102.0),
            ],
            lookback_rows=2,
        )
        replay_result = build_single_date_replay_rows(bundle)
        check_rows = build_fixture_check_replay_rows(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            horizons=["C"],
        )

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_single_date_replay_artifacts(
                output_root=Path(tmp) / "calibration",
                replay_result=replay_result,
                check_rows=check_rows,
            )

            with artifacts.replay_rows_csv_path.open(newline="", encoding="utf-8") as h:
                replay_csv_rows = list(csv.DictReader(h))
            with artifacts.check_rows_csv_path.open(newline="", encoding="utf-8") as h:
                check_csv_rows = list(csv.DictReader(h))
            manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
            diagnostics = json.loads(
                artifacts.market_data_diagnostics_path.read_text(encoding="utf-8")
            )

            with sqlite3.connect(artifacts.check_rows_sqlite_path) as conn:
                check_count = conn.execute(
                    f"SELECT COUNT(*) FROM {CHECK_REPLAY_ROWS_TABLE}"
                ).fetchone()[0]

        self.assertEqual(len(replay_csv_rows), 1)
        self.assertEqual(replay_csv_rows[0]["symbol"], "SPY")
        self.assertEqual(len(check_csv_rows), 30)
        self.assertEqual(check_count, 30)
        self.assertEqual(
            manifest["schema_version"],
            SINGLE_DATE_ARTIFACT_SCHEMA_VERSION,
        )
        self.assertEqual(manifest["replay"]["row_count"], 1)
        self.assertEqual(diagnostics["replay_date"], "2026-05-22")

    def test_writer_rejects_live_runtime_output_root(self) -> None:
        bundle = build_asof_input_bundle(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            price_rows=[_row("SPY", date(2026, 5, 22), 102.0)],
            lookback_rows=1,
        )
        replay_result = build_single_date_replay_rows(bundle)

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / ".cache" / "jerboa" / "runtime"

            with self.assertRaisesRegex(ValueError, "live runtime state"):
                write_single_date_replay_artifacts(
                    output_root=output_root,
                    replay_result=replay_result,
                    check_rows=[],
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
