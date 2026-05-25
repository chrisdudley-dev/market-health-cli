from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_review import (
    REVIEW_COLD,
    REVIEW_HOT,
    REVIEW_INCONCLUSIVE,
    build_glyph_calibration_review_rows,
    calibration_review_classification,
)
from market_health.calibration.residuals import ResidualAttributionRow


class CalibrationGlyphReviewBuilderTest(unittest.TestCase):
    def test_builds_hot_cold_and_inconclusive_glyph_review_rows(self) -> None:
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
            residual_row(
                symbol="XLF",
                category="D",
                slot=3,
                glyph="F",
                forecast_score=6.0,
                realized_current_score=6.0,
                residual=0.0,
                residual_direction="neutral",
            ),
        )

        review_rows = build_glyph_calibration_review_rows(
            rows,
            min_observation_count=2,
        )

        self.assertEqual(
            [(row.horizon, row.category_slot, row.glyph) for row in review_rows],
            [("H1", "B4", "+"), ("H1", "C2", "-"), ("H1", "D3", "F")],
        )

        hot = review_rows[0]
        cold = review_rows[1]
        inconclusive = review_rows[2]

        self.assertEqual(hot.observation_count, 3)
        self.assertEqual(hot.mean_residual, round((0.5 + 0.25 - 0.25) / 3, 8))
        self.assertEqual(hot.median_residual, 0.25)
        self.assertEqual(hot.mean_abs_residual, round((0.5 + 0.25 + 0.25) / 3, 8))
        self.assertEqual(hot.hot_count, 2)
        self.assertEqual(hot.cold_count, 1)
        self.assertEqual(hot.neutral_count, 0)
        self.assertEqual(hot.review_classification, REVIEW_HOT)

        self.assertEqual(cold.observation_count, 2)
        self.assertEqual(cold.mean_residual, -0.375)
        self.assertEqual(cold.median_residual, -0.375)
        self.assertEqual(cold.review_classification, REVIEW_COLD)

        self.assertEqual(inconclusive.observation_count, 1)
        self.assertEqual(inconclusive.neutral_count, 1)
        self.assertEqual(inconclusive.review_classification, REVIEW_INCONCLUSIVE)

    def test_preserves_window_metadata(self) -> None:
        review_rows = build_glyph_calibration_review_rows(
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
            window_label="30d",
            window_start_date=date(2026, 5, 1),
            window_end_date=date(2026, 5, 30),
        )

        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0].window_label, "30d")
        self.assertEqual(review_rows[0].window_start_date, date(2026, 5, 1))
        self.assertEqual(review_rows[0].window_end_date, date(2026, 5, 30))

    def test_rejects_mixed_run_ids_in_same_glyph_bucket(self) -> None:
        with self.assertRaisesRegex(ValueError, "residual_attribution_run_id"):
            build_glyph_calibration_review_rows(
                (
                    residual_row(residual_attribution_run_id="run-a"),
                    residual_row(symbol="QQQ", residual_attribution_run_id="run-b"),
                )
            )

    def test_classification_helper_preserves_min_n_rule(self) -> None:
        self.assertEqual(
            calibration_review_classification(
                observation_count=2,
                min_observation_count=3,
                mean_residual=0.5,
            ),
            REVIEW_INCONCLUSIVE,
        )
        self.assertEqual(
            calibration_review_classification(
                observation_count=3,
                min_observation_count=3,
                mean_residual=0.5,
            ),
            REVIEW_HOT,
        )
        self.assertEqual(
            calibration_review_classification(
                observation_count=3,
                min_observation_count=3,
                mean_residual=-0.5,
            ),
            REVIEW_COLD,
        )
        self.assertEqual(
            calibration_review_classification(
                observation_count=3,
                min_observation_count=3,
                mean_residual=0.0,
            ),
            REVIEW_INCONCLUSIVE,
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
