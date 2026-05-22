from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.warmup_window import (
    resolve_replay_warmup_window,
)


class ReplayWarmupWindowTest(unittest.TestCase):
    def test_resolver_uses_last_rows_on_or_before_replay_date(self) -> None:
        rows = [
            _row("SPY", date(2026, 5, 18), 100.0),
            _row("SPY", date(2026, 5, 20), 101.0),
            _row("SPY", date(2026, 5, 22), 102.0),
            _row("SPY", date(2026, 5, 26), 103.0),
        ]

        window = resolve_replay_warmup_window(
            rows,
            replay_date=date(2026, 5, 22),
            lookback_rows=2,
            symbols=["SPY"],
        )

        self.assertEqual(
            [(row.symbol, row.date.isoformat()) for row in window.rows],
            [("SPY", "2026-05-20"), ("SPY", "2026-05-22")],
        )
        self.assertEqual(window.start_date, date(2026, 5, 20))
        self.assertEqual(window.end_date, date(2026, 5, 22))
        self.assertEqual(window.row_count, 2)

    def test_resolver_handles_sparse_calendar_by_available_rows(self) -> None:
        rows = [
            _row("SPY", date(2026, 5, 1), 100.0),
            _row("SPY", date(2026, 5, 8), 101.0),
            _row("SPY", date(2026, 5, 22), 102.0),
        ]

        window = resolve_replay_warmup_window(
            rows,
            replay_date=date(2026, 5, 22),
            lookback_rows=2,
            symbols=["SPY"],
        )

        self.assertEqual(
            [row.date for row in window.rows],
            [date(2026, 5, 8), date(2026, 5, 22)],
        )

    def test_resolver_filters_symbols_and_reports_missing(self) -> None:
        rows = [
            _row("QQQ", date(2026, 5, 22), 200.0),
            _row("SPY", date(2026, 5, 22), 100.0),
        ]

        window = resolve_replay_warmup_window(
            rows,
            replay_date=date(2026, 5, 22),
            lookback_rows=3,
            symbols=["SPY", "IWM"],
        )

        self.assertEqual(window.available_symbols, ("SPY",))
        self.assertEqual(window.missing_symbols, ("IWM",))
        self.assertEqual(
            [(row.symbol, row.date.isoformat()) for row in window.rows],
            [("SPY", "2026-05-22")],
        )

    def test_resolver_orders_rows_by_symbol_then_date(self) -> None:
        rows = [
            _row("SPY", date(2026, 5, 22), 100.0),
            _row("QQQ", date(2026, 5, 22), 200.0),
            _row("SPY", date(2026, 5, 21), 99.0),
            _row("QQQ", date(2026, 5, 21), 199.0),
        ]

        window = resolve_replay_warmup_window(
            rows,
            replay_date=date(2026, 5, 22),
            lookback_rows=2,
        )

        self.assertEqual(
            [(row.symbol, row.date.isoformat()) for row in window.rows],
            [
                ("QQQ", "2026-05-21"),
                ("QQQ", "2026-05-22"),
                ("SPY", "2026-05-21"),
                ("SPY", "2026-05-22"),
            ],
        )

    def test_resolver_rejects_non_positive_lookback(self) -> None:
        with self.assertRaisesRegex(ValueError, "lookback_rows must be positive"):
            resolve_replay_warmup_window(
                [],
                replay_date=date(2026, 5, 22),
                lookback_rows=0,
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
