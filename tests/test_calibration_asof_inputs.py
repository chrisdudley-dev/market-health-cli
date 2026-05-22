from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.asof_inputs import (
    ASOF_INPUT_BUNDLE_SCHEMA_VERSION,
    AsOfInputBundle,
    build_asof_input_bundle,
)
from market_health.calibration.price_cache import HistoricalPriceRow


class AsOfInputBundleTest(unittest.TestCase):
    def test_bundle_filters_future_rows_and_reports_diagnostics(self) -> None:
        bundle = build_asof_input_bundle(
            replay_date=date(2026, 5, 22),
            symbols=["spy", "QQQ", "IWM"],
            price_rows=[
                _row("SPY", date(2026, 5, 20), 100.0),
                _row("SPY", date(2026, 5, 21), 101.0),
                _row("SPY", date(2026, 5, 22), 102.0),
                _row("SPY", date(2026, 5, 23), 103.0),
                _row("QQQ", date(2026, 5, 21), 201.0),
                _row("IWM", date(2026, 5, 23), 51.0),
            ],
            lookback_rows=2,
        )

        self.assertEqual(bundle.requested_symbols, ("SPY", "QQQ", "IWM"))
        self.assertEqual(bundle.eligible_symbols, ("SPY",))
        self.assertEqual(bundle.excluded_future_row_count, 2)
        self.assertTrue(all(row.date <= date(2026, 5, 22) for row in bundle.price_rows))
        self.assertEqual(
            [(row.symbol, row.date.isoformat()) for row in bundle.price_rows],
            [
                ("QQQ", "2026-05-21"),
                ("SPY", "2026-05-21"),
                ("SPY", "2026-05-22"),
            ],
        )
        self.assertEqual(bundle.market_data_diagnostics.missing_symbols, ("IWM",))
        self.assertEqual(
            bundle.market_data_diagnostics.missing_replay_date_symbols,
            ("QQQ", "IWM"),
        )
        self.assertEqual(
            bundle.market_data_diagnostics.partial_warmup_symbols,
            ("QQQ",),
        )

    def test_bundle_record_has_stable_shape(self) -> None:
        bundle = build_asof_input_bundle(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            price_rows=[
                _row("SPY", date(2026, 5, 21), 101.0),
                _row("SPY", date(2026, 5, 22), 102.0),
            ],
            lookback_rows=2,
        )

        record = bundle.to_record()

        self.assertEqual(
            record["schema_version"],
            ASOF_INPUT_BUNDLE_SCHEMA_VERSION,
        )
        self.assertEqual(record["replay_date"], "2026-05-22")
        self.assertEqual(record["requested_symbols"], ["SPY"])
        self.assertEqual(record["eligible_symbols"], ["SPY"])
        self.assertEqual(record["row_count"], 2)
        self.assertIn("market_data_diagnostics", record)

    def test_bundle_rejects_future_rows_if_constructed_directly(self) -> None:
        source = build_asof_input_bundle(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            price_rows=[_row("SPY", date(2026, 5, 22), 102.0)],
            lookback_rows=1,
        )

        with self.assertRaisesRegex(ValueError, "future rows"):
            AsOfInputBundle(
                replay_date=source.replay_date,
                lookback_rows=source.lookback_rows,
                requested_symbols=source.requested_symbols,
                eligible_symbols=source.eligible_symbols,
                price_rows=(_row("SPY", date(2026, 5, 23), 103.0),),
                warmup_window=source.warmup_window,
                market_data_diagnostics=source.market_data_diagnostics,
                excluded_future_row_count=1,
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
