from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.authoritative_dataset import (
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_MISSING,
    REALIZED_OUTCOME_NOT_APPLICABLE,
)
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.realized_outcomes import (
    REALIZED_FORWARD_OUTCOME_COLUMNS,
    REALIZED_FORWARD_OUTCOME_SCHEMA_VERSION,
    RealizedForwardOutcome,
    resolve_realized_forward_outcome,
    resolve_realized_forward_outcomes,
)


class RealizedForwardOutcomeTest(unittest.TestCase):
    def test_h1_available_outcome_uses_next_available_symbol_row(self) -> None:
        outcome = resolve_realized_forward_outcome(
            _rows(),
            replay_date=date(2026, 5, 20),
            symbol="spy",
            horizon="h1",
        )

        self.assertEqual(outcome.realized_outcome_status, REALIZED_OUTCOME_AVAILABLE)
        self.assertEqual(outcome.symbol, "SPY")
        self.assertEqual(outcome.horizon, "H1")
        self.assertEqual(outcome.target_offset, 1)
        self.assertEqual(outcome.target_date, date(2026, 5, 21))
        self.assertEqual(outcome.origin_adjusted_close, 100.0)
        self.assertEqual(outcome.target_adjusted_close, 103.0)
        self.assertEqual(outcome.realized_return, 0.03)
        self.assertEqual(outcome.realized_current_score, 8.0)
        self.assertEqual(outcome.source_row_count, 6)

    def test_h5_available_outcome_uses_fifth_available_future_row(self) -> None:
        outcome = resolve_realized_forward_outcome(
            _rows(),
            replay_date=date(2026, 5, 20),
            symbol="SPY",
            horizon="H5",
        )

        self.assertEqual(outcome.realized_outcome_status, REALIZED_OUTCOME_AVAILABLE)
        self.assertEqual(outcome.target_offset, 5)
        self.assertEqual(outcome.target_date, date(2026, 5, 28))
        self.assertEqual(outcome.target_adjusted_close, 110.0)
        self.assertEqual(outcome.realized_return, 0.1)
        self.assertEqual(outcome.realized_current_score, 10.0)

    def test_missing_outcome_when_future_rows_are_insufficient(self) -> None:
        outcome = resolve_realized_forward_outcome(
            _rows(),
            replay_date=date(2026, 5, 23),
            symbol="SPY",
            horizon="H5",
        )

        self.assertEqual(outcome.realized_outcome_status, REALIZED_OUTCOME_MISSING)
        self.assertEqual(outcome.target_offset, 5)
        self.assertIsNone(outcome.target_date)
        self.assertIsNone(outcome.realized_current_score)
        self.assertIsNone(outcome.realized_return)

    def test_missing_outcome_when_origin_row_is_missing(self) -> None:
        outcome = resolve_realized_forward_outcome(
            _rows(),
            replay_date=date(2026, 5, 22),
            symbol="QQQ",
            horizon="H1",
        )

        self.assertEqual(outcome.realized_outcome_status, REALIZED_OUTCOME_MISSING)
        self.assertEqual(outcome.source_row_count, 2)

    def test_current_horizon_is_not_applicable(self) -> None:
        outcome = resolve_realized_forward_outcome(
            _rows(),
            replay_date=date(2026, 5, 20),
            symbol="SPY",
            horizon="C",
        )

        self.assertEqual(
            outcome.realized_outcome_status,
            REALIZED_OUTCOME_NOT_APPLICABLE,
        )
        self.assertIsNone(outcome.target_date)
        self.assertIsNone(outcome.realized_current_score)

    def test_batch_resolver_normalizes_deduplicates_and_sorts(self) -> None:
        outcomes = resolve_realized_forward_outcomes(
            _rows(),
            replay_date=date(2026, 5, 20),
            symbols=[" spy ", "QQQ", "SPY"],
            horizons=["h5", "h1", "H1"],
        )

        self.assertEqual(
            [(item.symbol, item.horizon) for item in outcomes],
            [("QQQ", "H1"), ("QQQ", "H5"), ("SPY", "H1"), ("SPY", "H5")],
        )

    def test_record_has_stable_shape(self) -> None:
        outcome = resolve_realized_forward_outcome(
            _rows(),
            replay_date=date(2026, 5, 20),
            symbol="SPY",
            horizon="H1",
        )
        record = outcome.to_record()

        self.assertEqual(tuple(record.keys()), REALIZED_FORWARD_OUTCOME_COLUMNS)
        self.assertEqual(
            record["schema_version"], REALIZED_FORWARD_OUTCOME_SCHEMA_VERSION
        )
        self.assertEqual(record["replay_date"], "2026-05-20")
        self.assertEqual(record["symbol"], "SPY")
        self.assertEqual(record["horizon"], "H1")
        self.assertEqual(record["target_date"], "2026-05-21")

    def test_available_outcome_requires_all_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires target_offset"):
            RealizedForwardOutcome(
                replay_date=date(2026, 5, 20),
                symbol="SPY",
                horizon="H1",
                realized_outcome_status=REALIZED_OUTCOME_AVAILABLE,
            )

    def test_invalid_horizon_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported realized"):
            resolve_realized_forward_outcomes(
                _rows(),
                replay_date=date(2026, 5, 20),
                symbols=["SPY"],
                horizons=["BAD"],
            )


def _rows() -> tuple[HistoricalPriceRow, ...]:
    return (
        _row("SPY", date(2026, 5, 20), 100.0),
        _row("SPY", date(2026, 5, 21), 103.0),
        _row("SPY", date(2026, 5, 23), 105.0),
        _row("SPY", date(2026, 5, 26), 106.0),
        _row("SPY", date(2026, 5, 27), 108.0),
        _row("SPY", date(2026, 5, 28), 110.0),
        _row("QQQ", date(2026, 5, 20), 200.0),
        _row("QQQ", date(2026, 5, 21), 198.0),
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
