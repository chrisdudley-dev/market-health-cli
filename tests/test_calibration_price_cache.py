from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.price_cache import (
    HISTORICAL_PRICE_CACHE_COLUMNS,
    HISTORICAL_PRICE_CACHE_SCHEMA_VERSION,
    HistoricalPriceRow,
    historical_price_row_from_record,
    read_historical_price_cache_csv,
)


class HistoricalPriceCacheTest(unittest.TestCase):
    def test_historical_price_row_round_trips_to_record(self) -> None:
        row = HistoricalPriceRow(
            source="fixture",
            symbol="spy",
            date=date(2026, 5, 22),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            adjusted_close=100.25,
            volume=123456,
        )

        record = row.to_record()
        parsed = historical_price_row_from_record(record)

        self.assertEqual(row.symbol, "SPY")
        self.assertEqual(tuple(record), HISTORICAL_PRICE_CACHE_COLUMNS)
        self.assertEqual(parsed, row)

    def test_reader_filters_symbols_and_date_range_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            _write_price_fixture(
                path,
                [
                    _record("SPY", "2026-05-23", 103.0),
                    _record("QQQ", "2026-05-22", 202.0),
                    _record("SPY", "2026-05-21", 101.0),
                    _record("SPY", "2026-05-22", 102.0),
                    _record("IWM", "2026-05-22", 50.0),
                ],
            )

            result = read_historical_price_cache_csv(
                path,
                symbols=["SPY", "QQQ"],
                start_date=date(2026, 5, 22),
                end_date=date(2026, 5, 22),
            )

        self.assertEqual(
            [(row.symbol, row.date.isoformat(), row.close) for row in result.rows],
            [
                ("QQQ", "2026-05-22", 202.0),
                ("SPY", "2026-05-22", 102.0),
            ],
        )
        self.assertEqual(result.available_symbols, ("QQQ", "SPY"))
        self.assertEqual(result.missing_symbols, ())

    def test_reader_reports_missing_requested_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            _write_price_fixture(path, [_record("SPY", "2026-05-22", 102.0)])

            result = read_historical_price_cache_csv(
                path,
                symbols=["SPY", "IWM"],
                start_date=date(2026, 5, 22),
                end_date=date(2026, 5, 22),
            )

        self.assertEqual(result.available_symbols, ("SPY",))
        self.assertEqual(result.missing_symbols, ("IWM",))

    def test_reader_rejects_duplicate_symbol_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            _write_price_fixture(
                path,
                [
                    _record("SPY", "2026-05-22", 102.0),
                    _record("spy", "2026-05-22", 103.0),
                ],
            )

            with self.assertRaisesRegex(ValueError, "duplicate symbol/date"):
                read_historical_price_cache_csv(path)

    def test_reader_rejects_unsupported_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            record = _record("SPY", "2026-05-22", 102.0)
            record["schema_version"] = "historical_price_cache.v0"
            _write_price_fixture(path, [record])

            with self.assertRaisesRegex(ValueError, "unsupported"):
                read_historical_price_cache_csv(path)


def _record(symbol: str, price_date: str, close: float) -> dict[str, str]:
    return {
        "schema_version": HISTORICAL_PRICE_CACHE_SCHEMA_VERSION,
        "source": "fixture",
        "symbol": symbol,
        "date": price_date,
        "open": str(close - 1.0),
        "high": str(close + 1.0),
        "low": str(close - 2.0),
        "close": str(close),
        "adjusted_close": str(close),
        "volume": "1000",
    }


def _write_price_fixture(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=HISTORICAL_PRICE_CACHE_COLUMNS,
        )
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":
    unittest.main()
