from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.asof_inputs import build_asof_input_bundle
from market_health.calibration.check_output import build_fixture_check_replay_rows
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.single_date_artifacts import (
    write_single_date_replay_artifacts,
)
from market_health.calibration.single_date_replay import build_single_date_replay_rows


class FutureDataExclusionTest(unittest.TestCase):
    def test_bundle_excludes_future_rows_before_single_date_replay(self) -> None:
        bundle = _bundle_with_future_rows()

        self.assertEqual(bundle.excluded_future_row_count, 3)
        self.assertEqual(bundle.eligible_symbols, ("SPY",))
        self.assertTrue(
            all(row.date <= bundle.replay_date for row in bundle.price_rows)
        )

        replay_result = build_single_date_replay_rows(bundle)

        self.assertEqual(replay_result.row_count, 1)
        self.assertEqual(replay_result.rows[0].symbol, "SPY")
        self.assertEqual(
            replay_result.rows[0].audit_token,
            "single-date-asof:2026-05-22:SPY:2:102.0000",
        )

    def test_replay_record_contains_only_asof_price_rows(self) -> None:
        bundle = _bundle_with_future_rows()
        replay_result = build_single_date_replay_rows(bundle)
        record_text = json.dumps(replay_result.to_record(), sort_keys=True)

        self.assertEqual(
            replay_result.asof_input_record["excluded_future_row_count"],
            3,
        )
        self.assertEqual(
            [row.date.isoformat() for row in bundle.price_rows],
            ["2026-05-20", "2026-05-20", "2026-05-22"],
        )
        self.assertTrue(
            all(row.date <= bundle.replay_date for row in bundle.price_rows)
        )
        self.assertNotIn("2026-05-23", record_text)
        self.assertNotIn("2026-05-24", record_text)

    def test_check_rows_are_built_from_asof_eligible_symbols_only(self) -> None:
        bundle = _bundle_with_future_rows()
        check_rows = build_fixture_check_replay_rows(
            replay_date=bundle.replay_date,
            symbols=bundle.eligible_symbols,
            horizons=["C"],
        )

        self.assertEqual(len(check_rows), 30)
        self.assertEqual({row.symbol for row in check_rows}, {"SPY"})
        self.assertEqual({row.replay_date for row in check_rows}, {date(2026, 5, 22)})

    def test_artifact_outputs_do_not_persist_future_price_rows(self) -> None:
        bundle = _bundle_with_future_rows()
        replay_result = build_single_date_replay_rows(bundle)
        check_rows = build_fixture_check_replay_rows(
            replay_date=bundle.replay_date,
            symbols=bundle.eligible_symbols,
            horizons=["C"],
        )

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_single_date_replay_artifacts(
                output_root=Path(tmp) / "calibration",
                replay_result=replay_result,
                check_rows=check_rows,
            )

            manifest_text = artifacts.manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)

            with artifacts.replay_rows_csv_path.open(newline="", encoding="utf-8") as h:
                replay_csv_rows = list(csv.DictReader(h))

        self.assertEqual(len(replay_csv_rows), 1)
        self.assertEqual(replay_csv_rows[0]["symbol"], "SPY")
        self.assertEqual(
            manifest["replay"]["asof_input"]["excluded_future_row_count"],
            3,
        )
        self.assertNotIn("2026-05-23", manifest_text)
        self.assertNotIn("2026-05-24", manifest_text)


def _bundle_with_future_rows():
    return build_asof_input_bundle(
        replay_date=date(2026, 5, 22),
        symbols=["SPY", "QQQ"],
        price_rows=[
            _row("SPY", date(2026, 5, 20), 100.0),
            _row("SPY", date(2026, 5, 22), 102.0),
            _row("SPY", date(2026, 5, 23), 150.0),
            _row("SPY", date(2026, 5, 24), 160.0),
            _row("QQQ", date(2026, 5, 20), 200.0),
            _row("QQQ", date(2026, 5, 23), 300.0),
        ],
        lookback_rows=3,
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
