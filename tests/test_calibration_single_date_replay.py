from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.asof_inputs import build_asof_input_bundle
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.single_date_replay import (
    SINGLE_DATE_REPLAY_SCHEMA_VERSION,
    build_single_date_replay_rows,
)


class SingleDateReplayRowsTest(unittest.TestCase):
    def test_replay_rows_are_built_for_eligible_symbols_only(self) -> None:
        bundle = build_asof_input_bundle(
            replay_date=date(2026, 5, 22),
            symbols=["SPY", "QQQ", "IWM"],
            price_rows=[
                _row("SPY", date(2026, 5, 21), 100.0),
                _row("SPY", date(2026, 5, 22), 102.0),
                _row("SPY", date(2026, 5, 23), 104.0),
                _row("QQQ", date(2026, 5, 21), 200.0),
                _row("IWM", date(2026, 5, 23), 50.0),
            ],
            lookback_rows=2,
        )

        result = build_single_date_replay_rows(bundle)

        self.assertEqual(result.row_count, 1)
        self.assertEqual([row.symbol for row in result.rows], ["SPY"])
        self.assertEqual(bundle.excluded_future_row_count, 2)

    def test_replay_row_scores_and_record_are_deterministic(self) -> None:
        bundle = build_asof_input_bundle(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            price_rows=[
                _row("SPY", date(2026, 5, 21), 100.0),
                _row("SPY", date(2026, 5, 22), 102.0),
            ],
            lookback_rows=2,
        )

        result = build_single_date_replay_rows(bundle)
        row = result.rows[0]
        record = result.to_record()

        self.assertEqual(row.current_score, 7.0)
        self.assertEqual(row.h1_score, 9.0)
        self.assertEqual(row.h5_score, 10.0)
        self.assertEqual(row.blend_score, 8.6667)
        self.assertEqual(row.state, "GREEN")
        self.assertEqual(
            row.audit_token,
            "single-date-asof:2026-05-22:SPY:2:102.0000",
        )
        self.assertEqual(record["schema_version"], SINGLE_DATE_REPLAY_SCHEMA_VERSION)
        self.assertEqual(record["row_count"], 1)
        self.assertIn("engine_metadata", record)
        self.assertIn("asof_input", record)


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
