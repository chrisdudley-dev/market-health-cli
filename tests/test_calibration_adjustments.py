from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_adjustments import (
    CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION,
    CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE,
    CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE,
    CALIBRATION_ADJUSTMENT_SCOPE_GLYPH,
    CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK,
    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW,
    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW,
    CalibrationAdjustmentCandidateRow,
)


class CalibrationAdjustmentCandidateRowTest(unittest.TestCase):
    def test_glyph_candidate_record_has_stable_shape(self) -> None:
        candidate = glyph_candidate()

        self.assertEqual(
            candidate.to_record(),
            {
                "schema_version": CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION,
                "candidate_id": (
                    "calibration-adjustment-candidate:glyph:glyph_review:"
                    "30d:2026-04-21:2026-05-20:H1:B4:+:any_named_check:"
                    "hot:decrease_score:-0.25000000:residual-test:review-test"
                ),
                "candidate_scope": "glyph",
                "source_review_table": "glyph_review",
                "window_label": "30d",
                "window_start_date": "2026-04-21",
                "window_end_date": "2026-05-20",
                "horizon": "H1",
                "category": "B",
                "slot": 4,
                "category_slot": "B4",
                "glyph": "+",
                "named_check": None,
                "review_classification": "hot",
                "adjustment_direction": "decrease_score",
                "score_delta": -0.25,
                "observation_count": 12,
                "mean_residual": 0.5,
                "mean_abs_residual": 0.75,
                "residual_attribution_run_id": "residual-test",
                "calibration_review_run_id": "review-test",
                "dry_run_only": True,
            },
        )

    def test_named_check_candidate_allows_optional_category_context(self) -> None:
        candidate = named_check_candidate()

        record = candidate.to_record()

        self.assertEqual(record["candidate_scope"], "named_check")
        self.assertEqual(record["source_review_table"], "named_check_review")
        self.assertEqual(record["horizon"], "H5")
        self.assertIsNone(record["category"])
        self.assertIsNone(record["slot"])
        self.assertIsNone(record["category_slot"])
        self.assertIsNone(record["glyph"])
        self.assertEqual(record["named_check"], "trend_confirmed")
        self.assertEqual(record["review_classification"], "cold")
        self.assertEqual(record["adjustment_direction"], "increase_score")
        self.assertEqual(record["score_delta"], 0.2)

    def test_normalizes_horizon_and_category(self) -> None:
        candidate = glyph_candidate(horizon="h5", category="b")

        self.assertEqual(candidate.horizon, "H5")
        self.assertEqual(candidate.category, "B")
        self.assertEqual(candidate.category_slot, "B4")

    def test_rejects_invalid_schema_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported"):
            glyph_candidate(schema_version="bad.v1")

    def test_rejects_non_dry_run_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "dry-run only"):
            glyph_candidate(dry_run_only=False)

    def test_rejects_scope_source_table_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "scope does not match"):
            glyph_candidate(
                source_review_table=(
                    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW
                )
            )

    def test_rejects_missing_glyph_scope_context(self) -> None:
        with self.assertRaisesRegex(ValueError, "category, slot, and glyph"):
            glyph_candidate(glyph=None)

    def test_rejects_named_check_scope_without_named_check(self) -> None:
        with self.assertRaisesRegex(ValueError, "require named_check"):
            named_check_candidate(named_check=None)

    def test_rejects_named_check_scope_with_partial_category_slot(self) -> None:
        with self.assertRaisesRegex(ValueError, "category and slot together"):
            named_check_candidate(category="B", slot=None)

    def test_rejects_inconclusive_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "review classification"):
            glyph_candidate(review_classification="inconclusive")

    def test_rejects_hot_candidate_that_does_not_decrease_score(self) -> None:
        with self.assertRaisesRegex(ValueError, "must decrease score"):
            glyph_candidate(
                adjustment_direction=CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE,
                score_delta=0.25,
            )

    def test_rejects_cold_candidate_that_does_not_increase_score(self) -> None:
        with self.assertRaisesRegex(ValueError, "must increase score"):
            named_check_candidate(
                adjustment_direction=CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE,
                score_delta=-0.2,
            )

    def test_rejects_bad_window_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "window_start_date"):
            glyph_candidate(
                window_start_date=date(2026, 5, 20),
                window_end_date=date(2026, 4, 21),
            )


def glyph_candidate(**overrides: object) -> CalibrationAdjustmentCandidateRow:
    values = {
        "candidate_scope": CALIBRATION_ADJUSTMENT_SCOPE_GLYPH,
        "source_review_table": CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW,
        "horizon": "H1",
        "category": "B",
        "slot": 4,
        "glyph": "+",
        "review_classification": "hot",
        "adjustment_direction": CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE,
        "score_delta": -0.25,
        "observation_count": 12,
        "mean_residual": 0.5,
        "mean_abs_residual": 0.75,
        "residual_attribution_run_id": "residual-test",
        "calibration_review_run_id": "review-test",
        "window_label": "30d",
        "window_start_date": date(2026, 4, 21),
        "window_end_date": date(2026, 5, 20),
    }
    values.update(overrides)
    return CalibrationAdjustmentCandidateRow(**values)


def named_check_candidate(**overrides: object) -> CalibrationAdjustmentCandidateRow:
    values = {
        "candidate_scope": CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK,
        "source_review_table": (CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW),
        "horizon": "H5",
        "named_check": "trend_confirmed",
        "review_classification": "cold",
        "adjustment_direction": CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE,
        "score_delta": 0.2,
        "observation_count": 8,
        "mean_residual": -0.4,
        "mean_abs_residual": 0.6,
        "residual_attribution_run_id": "residual-test",
        "calibration_review_run_id": "review-test",
    }
    values.update(overrides)
    return CalibrationAdjustmentCandidateRow(**values)


if __name__ == "__main__":
    unittest.main()
