from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.authoritative_dataset import (
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_NOT_APPLICABLE,
)
from market_health.calibration.authoritative_dataset_builder import (
    build_authoritative_replay_dataset_rows,
)
from market_health.calibration.check_output import (
    MEASUREMENT_MEASURED,
    CheckReplayRow,
)
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.range_request import build_range_replay_request
from market_health.calibration.range_runner import run_range_replay


class AuthoritativeDatasetBuilderTest(unittest.TestCase):
    def test_builds_rows_from_range_replay_check_rows_and_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            price_rows = _price_rows()
            range_result = _range_result(Path(tmp), price_rows)
            dataset_rows = build_authoritative_replay_dataset_rows(
                range_result=range_result,
                check_rows=[
                    _check("SPY", "H5", slot=1),
                    _check("SPY", "C", slot=1),
                    _check("SPY", "H1", slot=1),
                ],
                price_rows=price_rows,
                dataset_run_id="dataset-test",
            )

        self.assertEqual(
            [(row.category_slot, row.horizon) for row in dataset_rows],
            [("A1", "C"), ("A1", "H1"), ("A1", "H5")],
        )
        current, h1, h5 = dataset_rows

        self.assertEqual(
            current.realized_outcome_status, REALIZED_OUTCOME_NOT_APPLICABLE
        )
        self.assertIsNone(current.target_date)
        self.assertEqual(h1.realized_outcome_status, REALIZED_OUTCOME_AVAILABLE)
        self.assertEqual(h1.target_date, date(2026, 5, 21))
        self.assertEqual(h1.realized_return, 0.03)
        self.assertEqual(h1.dataset_run_id, "dataset-test")
        self.assertEqual(h5.realized_outcome_status, REALIZED_OUTCOME_AVAILABLE)
        self.assertEqual(h5.target_date, date(2026, 5, 28))
        self.assertEqual(h5.realized_return, 0.1)

    def test_preserves_replay_and_check_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            price_rows = _price_rows()
            range_result = _range_result(Path(tmp), price_rows)
            rows = build_authoritative_replay_dataset_rows(
                range_result=range_result,
                check_rows=[_check("SPY", "H1", category="B", slot=2)],
                price_rows=price_rows,
            )

        row = rows[0]
        replay_row = range_result.results[0].rows[0]
        self.assertEqual(row.replay_date, date(2026, 5, 20))
        self.assertEqual(row.symbol, "SPY")
        self.assertEqual(row.current_score, replay_row.current_score)
        self.assertEqual(row.h1_score, replay_row.h1_score)
        self.assertEqual(row.h5_score, replay_row.h5_score)
        self.assertEqual(row.blend_score, replay_row.blend_score)
        self.assertEqual(row.state, replay_row.state)
        self.assertEqual(row.audit_token, replay_row.audit_token)
        self.assertEqual(row.category, "B")
        self.assertEqual(row.slot, 2)
        self.assertEqual(row.category_slot, "B2")
        self.assertEqual(row.glyph, "h2")
        self.assertEqual(row.named_check, "Check B2")
        self.assertEqual(row.check_score, 2.1)
        self.assertEqual(row.measurement_status, MEASUREMENT_MEASURED)

    def test_missing_matching_replay_row_raises_key_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            price_rows = _price_rows()
            range_result = _range_result(Path(tmp), price_rows)

            with self.assertRaisesRegex(KeyError, "no matching replay row"):
                build_authoritative_replay_dataset_rows(
                    range_result=range_result,
                    check_rows=[_check("QQQ", "H1")],
                    price_rows=price_rows,
                )

    def test_missing_forward_outcome_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            price_rows = _price_rows()[:2]
            range_result = _range_result(Path(tmp), price_rows)
            rows = build_authoritative_replay_dataset_rows(
                range_result=range_result,
                check_rows=[_check("SPY", "H5")],
                price_rows=price_rows,
            )

        self.assertEqual(rows[0].realized_outcome_status, "missing")
        self.assertIsNone(rows[0].target_date)
        self.assertIsNone(rows[0].realized_current_score)

    def test_rows_are_sorted_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            price_rows = _price_rows()
            range_result = _range_result(Path(tmp), price_rows)
            rows = build_authoritative_replay_dataset_rows(
                range_result=range_result,
                check_rows=[
                    _check("SPY", "H5", category="B", slot=2),
                    _check("SPY", "H1", category="A", slot=2),
                    _check("SPY", "C", category="A", slot=1),
                ],
                price_rows=price_rows,
            )

        self.assertEqual(
            [(row.category, row.slot, row.horizon) for row in rows],
            [("A", 1, "C"), ("A", 2, "H1"), ("B", 2, "H5")],
        )


def _range_result(output_root: Path, price_rows: tuple[HistoricalPriceRow, ...]):
    request = build_range_replay_request(
        start_date=date(2026, 5, 20),
        end_date=date(2026, 5, 20),
        symbols=["SPY"],
        lookback_rows=1,
        output_root=output_root / "calibration",
    )
    return run_range_replay(request=request, price_rows=price_rows)


def _check(
    symbol: str,
    horizon: str,
    *,
    category: str = "A",
    slot: int = 1,
) -> CheckReplayRow:
    return CheckReplayRow(
        replay_date=date(2026, 5, 20),
        symbol=symbol,
        category=category,
        slot=slot,
        horizon=horizon,
        glyph=f"{horizon.lower()[0]}{slot}",
        named_check=f"Check {category}{slot}",
        score=float(slot) + {"C": 0.0, "H1": 0.1, "H5": 0.2}[horizon],
        replayability_class="replayable",
        measurement_status=MEASUREMENT_MEASURED,
        source_module="fixture.module",
        function_name=f"check_{category.lower()}{slot}",
    )


def _price_rows() -> tuple[HistoricalPriceRow, ...]:
    return (
        _row("SPY", date(2026, 5, 20), 100.0),
        _row("SPY", date(2026, 5, 21), 103.0),
        _row("SPY", date(2026, 5, 23), 105.0),
        _row("SPY", date(2026, 5, 26), 106.0),
        _row("SPY", date(2026, 5, 27), 108.0),
        _row("SPY", date(2026, 5, 28), 110.0),
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
