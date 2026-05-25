from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_adjustments import (
    CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE,
    CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE,
    CALIBRATION_ADJUSTMENT_SCOPE_GLYPH,
    CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK,
    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW,
    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW,
    build_calibration_adjustment_candidates_from_review_tables,
    build_glyph_calibration_adjustment_candidates,
    build_named_check_calibration_adjustment_candidates,
)
from market_health.calibration.calibration_review import (
    CalibrationGlyphReviewRow,
    CalibrationNamedCheckReviewRow,
)


class CalibrationAdjustmentCandidateBuilderTest(unittest.TestCase):
    def test_builds_glyph_candidates_from_hot_and_cold_review_rows(self) -> None:
        candidates = build_glyph_calibration_adjustment_candidates(
            (
                glyph_review_row(review_classification="hot", mean_residual=0.5),
                glyph_review_row(
                    category="C",
                    slot=2,
                    glyph="-",
                    review_classification="cold",
                    mean_residual=-0.25,
                    mean_abs_residual=0.3,
                ),
                glyph_review_row(
                    category="D",
                    slot=3,
                    glyph="F",
                    observation_count=2,
                    min_observation_count=3,
                    review_classification="inconclusive",
                    mean_residual=0.7,
                ),
            ),
            calibration_review_run_id="review-test",
            min_observation_count=3,
        )

        self.assertEqual(len(candidates), 2)
        candidates_by_slot = {
            candidate.category_slot: candidate for candidate in candidates
        }
        cold = candidates_by_slot["C2"]
        hot = candidates_by_slot["B4"]

        self.assertEqual(cold.candidate_scope, CALIBRATION_ADJUSTMENT_SCOPE_GLYPH)
        self.assertEqual(
            cold.source_review_table,
            CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW,
        )
        self.assertEqual(cold.category_slot, "C2")
        self.assertEqual(cold.glyph, "-")
        self.assertEqual(cold.review_classification, "cold")
        self.assertEqual(
            cold.adjustment_direction,
            CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE,
        )
        self.assertEqual(cold.score_delta, 0.25)

        self.assertEqual(hot.category_slot, "B4")
        self.assertEqual(hot.glyph, "+")
        self.assertEqual(hot.review_classification, "hot")
        self.assertEqual(
            hot.adjustment_direction,
            CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE,
        )
        self.assertEqual(hot.score_delta, -0.5)
        self.assertEqual(hot.window_label, "30d")
        self.assertEqual(hot.window_start_date, date(2026, 4, 21))
        self.assertEqual(hot.window_end_date, date(2026, 5, 20))
        self.assertEqual(hot.residual_attribution_run_id, "residual-test")
        self.assertEqual(hot.calibration_review_run_id, "review-test")

    def test_builds_named_check_candidates_and_preserves_optional_context(
        self,
    ) -> None:
        candidates = build_named_check_calibration_adjustment_candidates(
            (
                named_check_review_row(
                    named_check="breadth_confirmed",
                    category="C",
                    slot=2,
                    glyph="-",
                    review_classification="cold",
                    mean_residual=-0.4,
                ),
                named_check_review_row(
                    named_check="trend_confirmed",
                    category=None,
                    slot=None,
                    glyph=None,
                    review_classification="hot",
                    mean_residual=0.2,
                ),
                named_check_review_row(
                    named_check="macro_filter",
                    observation_count=1,
                    min_observation_count=3,
                    review_classification="inconclusive",
                    mean_residual=-0.8,
                ),
            ),
            calibration_review_run_id="review-test",
            min_observation_count=3,
        )

        self.assertEqual(len(candidates), 2)
        breadth, trend = candidates

        self.assertEqual(
            breadth.candidate_scope,
            CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK,
        )
        self.assertEqual(
            breadth.source_review_table,
            CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW,
        )
        self.assertEqual(breadth.named_check, "breadth_confirmed")
        self.assertEqual(breadth.category_slot, "C2")
        self.assertEqual(breadth.glyph, "-")
        self.assertEqual(breadth.score_delta, 0.4)

        self.assertEqual(trend.named_check, "trend_confirmed")
        self.assertIsNone(trend.category)
        self.assertIsNone(trend.slot)
        self.assertIsNone(trend.category_slot)
        self.assertIsNone(trend.glyph)
        self.assertEqual(trend.score_delta, -0.2)

    def test_combined_builder_sorts_candidates_deterministically(self) -> None:
        candidates = build_calibration_adjustment_candidates_from_review_tables(
            glyph_review_rows=(
                glyph_review_row(
                    category="C",
                    slot=2,
                    glyph="-",
                    review_classification="cold",
                    mean_residual=-0.25,
                ),
                glyph_review_row(review_classification="hot", mean_residual=0.5),
            ),
            named_check_review_rows=(
                named_check_review_row(
                    named_check="trend_confirmed",
                    review_classification="hot",
                    mean_residual=0.2,
                ),
            ),
            calibration_review_run_id="review-test",
            min_observation_count=3,
        )

        candidate_ids = [candidate.candidate_id for candidate in candidates]

        self.assertEqual(candidate_ids, sorted(candidate_ids))

    def test_skips_rows_below_builder_min_observation_count(self) -> None:
        candidates = build_glyph_calibration_adjustment_candidates(
            (
                glyph_review_row(
                    observation_count=3,
                    min_observation_count=1,
                    review_classification="hot",
                    mean_residual=0.5,
                ),
            ),
            min_observation_count=4,
        )

        self.assertEqual(candidates, ())

    def test_rejects_invalid_builder_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibration_review_run_id"):
            build_glyph_calibration_adjustment_candidates(
                (),
                calibration_review_run_id=" ",
            )

        with self.assertRaisesRegex(ValueError, "min_observation_count"):
            build_named_check_calibration_adjustment_candidates(
                (),
                min_observation_count=0,
            )


def glyph_review_row(**overrides: object) -> CalibrationGlyphReviewRow:
    values = {
        "horizon": "H1",
        "category": "B",
        "slot": 4,
        "glyph": "+",
        "observation_count": 4,
        "min_observation_count": 3,
        "mean_residual": 0.5,
        "median_residual": 0.4,
        "mean_abs_residual": 0.6,
        "hot_count": 4,
        "cold_count": 0,
        "neutral_count": 0,
        "review_classification": "hot",
        "residual_attribution_run_id": "residual-test",
        "window_label": "30d",
        "window_start_date": date(2026, 4, 21),
        "window_end_date": date(2026, 5, 20),
    }
    values.update(overrides)
    _balance_review_direction_counts(values)
    return CalibrationGlyphReviewRow(**values)


def named_check_review_row(**overrides: object) -> CalibrationNamedCheckReviewRow:
    values = {
        "horizon": "H1",
        "named_check": "trend_confirmed",
        "category": "B",
        "slot": 4,
        "glyph": "+",
        "observation_count": 4,
        "min_observation_count": 3,
        "mean_residual": 0.5,
        "median_residual": 0.4,
        "mean_abs_residual": 0.6,
        "hot_count": 4,
        "cold_count": 0,
        "neutral_count": 0,
        "review_classification": "hot",
        "residual_attribution_run_id": "residual-test",
        "window_label": "30d",
        "window_start_date": date(2026, 4, 21),
        "window_end_date": date(2026, 5, 20),
    }
    values.update(overrides)
    _balance_review_direction_counts(values)
    return CalibrationNamedCheckReviewRow(**values)


def _balance_review_direction_counts(values: dict[str, object]) -> None:
    observation_count = int(values["observation_count"])
    classification = values["review_classification"]
    values["hot_count"] = observation_count if classification == "hot" else 0
    values["cold_count"] = observation_count if classification == "cold" else 0
    values["neutral_count"] = (
        observation_count if classification == "inconclusive" else 0
    )


if __name__ == "__main__":
    unittest.main()
