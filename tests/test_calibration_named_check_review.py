from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_review import (
    REVIEW_COLD,
    REVIEW_HOT,
    REVIEW_INCONCLUSIVE,
    build_named_check_calibration_review_rows,
)
from market_health.calibration.residuals import ResidualAttributionRow


class CalibrationNamedCheckReviewBuilderTest(unittest.TestCase):
    def test_builds_named_check_review_rows(self) -> None:
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
                forecast_score=7.75,
                realized_current_score=8.0,
                residual=-0.25,
                residual_direction="cold",
            ),
            residual_row(
                symbol="DIA",
                named_check="breadth_confirmed",
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
                named_check="breadth_confirmed",
                category="C",
                slot=2,
                glyph="-",
                forecast_score=7.0,
                realized_current_score=7.25,
                residual=-0.25,
                residual_direction="cold",
            ),
            residual_row(
                symbol="XLF",
                named_check="macro_filter",
                category="D",
                slot=3,
                glyph="F",
                forecast_score=6.0,
                realized_current_score=6.0,
                residual=0.0,
                residual_direction="neutral",
            ),
        )

        review_rows = build_named_check_calibration_review_rows(
            rows,
            min_observation_count=2,
        )

        self.assertEqual(
            [(row.horizon, row.named_check) for row in review_rows],
            [
                ("H1", "breadth_confirmed"),
                ("H1", "macro_filter"),
                ("H1", "trend_confirmed"),
            ],
        )

        cold = review_rows[0]
        inconclusive = review_rows[1]
        hot = review_rows[2]

        self.assertEqual(cold.category, "C")
        self.assertEqual(cold.slot, 2)
        self.assertEqual(cold.category_slot, "C2")
        self.assertEqual(cold.glyph, "-")
        self.assertEqual(cold.observation_count, 2)
        self.assertEqual(cold.mean_residual, -0.375)
        self.assertEqual(cold.median_residual, -0.375)
        self.assertEqual(cold.hot_count, 0)
        self.assertEqual(cold.cold_count, 2)
        self.assertEqual(cold.neutral_count, 0)
        self.assertEqual(cold.review_classification, REVIEW_COLD)

        self.assertEqual(inconclusive.category, "D")
        self.assertEqual(inconclusive.slot, 3)
        self.assertEqual(inconclusive.category_slot, "D3")
        self.assertEqual(inconclusive.glyph, "F")
        self.assertEqual(inconclusive.observation_count, 1)
        self.assertEqual(inconclusive.neutral_count, 1)
        self.assertEqual(inconclusive.review_classification, REVIEW_INCONCLUSIVE)

        self.assertEqual(hot.category, "B")
        self.assertEqual(hot.slot, 4)
        self.assertEqual(hot.category_slot, "B4")
        self.assertEqual(hot.glyph, "+")
        self.assertEqual(hot.observation_count, 3)
        self.assertEqual(hot.mean_residual, round((0.5 + 0.25 - 0.25) / 3, 8))
        self.assertEqual(hot.mean_abs_residual, round((0.5 + 0.25 + 0.25) / 3, 8))
        self.assertEqual(hot.review_classification, REVIEW_HOT)

    def test_omits_ambiguous_category_context_for_repeated_named_check(self) -> None:
        review_rows = build_named_check_calibration_review_rows(
            (
                residual_row(),
                residual_row(
                    symbol="QQQ",
                    category="C",
                    slot=2,
                    glyph="-",
                    forecast_score=8.25,
                    realized_current_score=8.0,
                    residual=0.25,
                ),
            ),
            min_observation_count=1,
        )

        self.assertEqual(len(review_rows), 1)
        row = review_rows[0]
        self.assertEqual(row.named_check, "trend_confirmed")
        self.assertIsNone(row.category)
        self.assertIsNone(row.slot)
        self.assertIsNone(row.category_slot)
        self.assertIsNone(row.glyph)

    def test_preserves_window_metadata(self) -> None:
        review_rows = build_named_check_calibration_review_rows(
            (
                residual_row(),
                residual_row(
                    symbol="QQQ",
                    forecast_score=8.25,
                    realized_current_score=8.0,
                    residual=0.25,
                ),
            ),
            min_observation_count=1,
            window_label="60d",
            window_start_date=date(2026, 4, 1),
            window_end_date=date(2026, 5, 30),
        )

        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0].window_label, "60d")
        self.assertEqual(review_rows[0].window_start_date, date(2026, 4, 1))
        self.assertEqual(review_rows[0].window_end_date, date(2026, 5, 30))

    def test_rejects_mixed_run_ids_in_same_named_check_bucket(self) -> None:
        with self.assertRaisesRegex(ValueError, "residual_attribution_run_id"):
            build_named_check_calibration_review_rows(
                (
                    residual_row(residual_attribution_run_id="run-a"),
                    residual_row(symbol="QQQ", residual_attribution_run_id="run-b"),
                )
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
        audit_token=f"single-date-asof:2026-05-20:{symbol}:1:100.0000",
        dataset_run_id="dataset-test",
        residual_attribution_run_id=residual_attribution_run_id,
    )


if __name__ == "__main__":
    unittest.main()
