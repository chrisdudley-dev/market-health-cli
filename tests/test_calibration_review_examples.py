from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_review import (
    CALIBRATION_REVIEW_EXAMPLE_COLUMNS,
    CALIBRATION_REVIEW_EXAMPLE_ROW_SCHEMA_VERSION,
    REVIEW_TABLE_GLYPH,
    REVIEW_TABLE_NAMED_CHECK,
    CalibrationReviewExampleRow,
    build_glyph_calibration_review_example_rows,
    build_named_check_calibration_review_example_rows,
)
from market_health.calibration.residuals import ResidualAttributionRow


class CalibrationReviewExampleRowTest(unittest.TestCase):
    def test_record_has_stable_shape(self) -> None:
        row = example_row()

        record = row.to_record()

        self.assertEqual(tuple(record.keys()), CALIBRATION_REVIEW_EXAMPLE_COLUMNS)
        self.assertEqual(
            record["schema_version"],
            CALIBRATION_REVIEW_EXAMPLE_ROW_SCHEMA_VERSION,
        )
        self.assertEqual(record["review_table"], REVIEW_TABLE_GLYPH)
        self.assertEqual(record["window_label"], "full")
        self.assertIsNone(record["window_start_date"])
        self.assertIsNone(record["window_end_date"])
        self.assertEqual(record["horizon"], "H1")
        self.assertEqual(record["category"], "B")
        self.assertEqual(record["slot"], 4)
        self.assertEqual(record["category_slot"], "B4")
        self.assertEqual(record["glyph"], "+")
        self.assertEqual(record["named_check"], "trend_confirmed")
        self.assertEqual(record["example_rank"], 1)
        self.assertEqual(record["replay_date"], "2026-05-20")
        self.assertEqual(record["target_date"], "2026-05-21")
        self.assertEqual(record["symbol"], "SPY")
        self.assertEqual(record["forecast_score"], 8.5)
        self.assertEqual(record["realized_current_score"], 8.0)
        self.assertEqual(record["residual"], 0.5)
        self.assertEqual(record["residual_direction"], "hot")
        self.assertEqual(record["audit_token"], "audit-spy")
        self.assertEqual(record["residual_attribution_run_id"], "m53-test")

    def test_normalizes_symbol_horizon_and_category(self) -> None:
        row = example_row(
            symbol=" spy ",
            horizon=" h5 ",
            category=" b ",
            slot=5,
        )

        self.assertEqual(row.symbol, "SPY")
        self.assertEqual(row.horizon, "H5")
        self.assertEqual(row.category, "B")
        self.assertEqual(row.category_slot, "B5")

    def test_rejects_invalid_table(self) -> None:
        with self.assertRaisesRegex(ValueError, "table"):
            example_row(review_table="bad")

    def test_rejects_non_positive_rank(self) -> None:
        with self.assertRaisesRegex(ValueError, "example_rank"):
            example_row(example_rank=0)


class CalibrationReviewExampleBuilderTest(unittest.TestCase):
    def test_builds_glyph_examples_by_absolute_residual(self) -> None:
        rows = (
            residual_row(symbol="SPY", residual=0.5, residual_direction="hot"),
            residual_row(
                symbol="QQQ",
                forecast_score=8.25,
                realized_current_score=8.0,
                residual=0.25,
                residual_direction="hot",
            ),
            residual_row(
                symbol="IWM",
                forecast_score=7.25,
                realized_current_score=8.0,
                residual=-0.75,
                residual_direction="cold",
            ),
            residual_row(
                symbol="DIA",
                category="C",
                slot=2,
                glyph="-",
                forecast_score=7.25,
                realized_current_score=7.75,
                residual=-0.5,
                residual_direction="cold",
            ),
            residual_row(
                symbol="XLK",
                category="C",
                slot=2,
                glyph="-",
                forecast_score=7.0,
                realized_current_score=7.25,
                residual=-0.25,
                residual_direction="cold",
            ),
        )

        examples = build_glyph_calibration_review_example_rows(
            rows,
            max_examples_per_group=2,
        )

        self.assertEqual(
            [
                (
                    row.review_table,
                    row.category_slot,
                    row.glyph,
                    row.example_rank,
                    row.symbol,
                )
                for row in examples
            ],
            [
                (REVIEW_TABLE_GLYPH, "B4", "+", 1, "IWM"),
                (REVIEW_TABLE_GLYPH, "B4", "+", 2, "SPY"),
                (REVIEW_TABLE_GLYPH, "C2", "-", 1, "DIA"),
                (REVIEW_TABLE_GLYPH, "C2", "-", 2, "XLK"),
            ],
        )
        self.assertEqual(examples[0].residual, -0.75)
        self.assertEqual(examples[1].residual, 0.5)

    def test_builds_named_check_examples_by_absolute_residual(self) -> None:
        rows = (
            residual_row(symbol="SPY", residual=0.5, residual_direction="hot"),
            residual_row(
                symbol="QQQ",
                forecast_score=8.25,
                realized_current_score=8.0,
                residual=0.25,
                residual_direction="hot",
            ),
            residual_row(
                symbol="IWM",
                named_check="breadth_confirmed",
                category="C",
                slot=2,
                glyph="-",
                forecast_score=7.25,
                realized_current_score=8.0,
                residual=-0.75,
                residual_direction="cold",
            ),
        )

        examples = build_named_check_calibration_review_example_rows(
            rows,
            max_examples_per_group=1,
        )

        self.assertEqual(
            [
                (row.review_table, row.named_check, row.example_rank, row.symbol)
                for row in examples
            ],
            [
                (REVIEW_TABLE_NAMED_CHECK, "breadth_confirmed", 1, "IWM"),
                (REVIEW_TABLE_NAMED_CHECK, "trend_confirmed", 1, "SPY"),
            ],
        )

    def test_preserves_window_metadata(self) -> None:
        examples = build_glyph_calibration_review_example_rows(
            (residual_row(),),
            window_label="30d",
            window_start_date=date(2026, 5, 1),
            window_end_date=date(2026, 5, 30),
        )

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0].window_label, "30d")
        self.assertEqual(examples[0].window_start_date, date(2026, 5, 1))
        self.assertEqual(examples[0].window_end_date, date(2026, 5, 30))

    def test_rejects_non_positive_example_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_examples_per_group"):
            build_glyph_calibration_review_example_rows(
                (residual_row(),),
                max_examples_per_group=0,
            )


def example_row(
    *,
    review_table: str = REVIEW_TABLE_GLYPH,
    horizon: str = "H1",
    category: str = "B",
    slot: int = 4,
    glyph: str = "+",
    named_check: str = "trend_confirmed",
    example_rank: int = 1,
    replay_date: date = date(2026, 5, 20),
    target_date: date = date(2026, 5, 21),
    symbol: str = "SPY",
    forecast_score: float = 8.5,
    realized_current_score: float = 8.0,
    residual: float = 0.5,
    residual_direction: str = "hot",
    audit_token: str = "audit-spy",
    residual_attribution_run_id: str = "m53-test",
) -> CalibrationReviewExampleRow:
    return CalibrationReviewExampleRow(
        review_table=review_table,
        horizon=horizon,
        category=category,
        slot=slot,
        glyph=glyph,
        named_check=named_check,
        example_rank=example_rank,
        replay_date=replay_date,
        target_date=target_date,
        symbol=symbol,
        forecast_score=forecast_score,
        realized_current_score=realized_current_score,
        residual=residual,
        residual_direction=residual_direction,
        audit_token=audit_token,
        residual_attribution_run_id=residual_attribution_run_id,
    )


def residual_row(
    *,
    symbol: str = "SPY",
    replay_date: date = date(2026, 5, 20),
    horizon: str = "H1",
    category: str = "B",
    slot: int = 4,
    glyph: str = "+",
    named_check: str = "trend_confirmed",
    forecast_score: float = 8.5,
    realized_current_score: float = 8.0,
    residual: float = 0.5,
    residual_direction: str = "hot",
    residual_attribution_run_id: str = "m53-test",
) -> ResidualAttributionRow:
    return ResidualAttributionRow(
        replay_date=replay_date,
        symbol=symbol,
        horizon=horizon,
        target_date=date(2026, 5, 21),
        forecast_score=forecast_score,
        realized_current_score=realized_current_score,
        residual=residual,
        residual_direction=residual_direction,
        realized_return=0.03,
        category=category,
        slot=slot,
        glyph=glyph,
        named_check=named_check,
        check_score=4.1,
        replayability_class="replayable",
        measurement_status="measured",
        source_module="fixture.module",
        function_name="check_b4",
        audit_token=f"audit-{symbol.lower()}",
        dataset_run_id="dataset-test",
        residual_attribution_run_id=residual_attribution_run_id,
    )


if __name__ == "__main__":
    unittest.main()
