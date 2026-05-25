from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.check_output import (
    ReviewedCheckScoreCalibrationAdjustment,
    apply_reviewed_check_score_calibration_adjustments,
    build_fixture_check_replay_rows,
)


class ReviewedCheckScoreCalibrationAdjustmentTest(unittest.TestCase):
    def test_adjustment_record_has_stable_shape(self) -> None:
        adjustment = reviewed_adjustment()

        record = adjustment.to_record()

        self.assertEqual(
            list(record),
            [
                "schema_version",
                "horizon",
                "category",
                "slot",
                "category_slot",
                "score_delta",
                "calibration_review_run_id",
                "dry_run_simulation_run_id",
                "approved_by",
                "rationale",
            ],
        )
        self.assertEqual(record["horizon"], "H5")
        self.assertEqual(record["category_slot"], "B3")
        self.assertEqual(record["score_delta"], -0.25)

    def test_rejects_unreviewed_or_invalid_adjustment(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved_by"):
            reviewed_adjustment(approved_by=" ")

        with self.assertRaisesRegex(ValueError, "score_delta"):
            reviewed_adjustment(score_delta=0.0)

        with self.assertRaisesRegex(ValueError, "horizon"):
            reviewed_adjustment(horizon="H2")

    def test_turns_down_only_matching_category_slot_and_horizon(self) -> None:
        rows = build_fixture_check_replay_rows(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            reviewed_calibration_adjustments=(reviewed_adjustment(),),
        )
        by_key = {
            (row.category_slot, row.horizon): row
            for row in rows
            if row.category in {"B", "C"}
        }

        self.assertEqual(by_key[("B3", "H5")].score, 2.95)
        self.assertEqual(by_key[("B3", "H1")].score, 3.1)
        self.assertEqual(by_key[("B4", "H5")].score, 4.2)
        self.assertEqual(by_key[("C3", "H5")].score, 3.2)

    def test_apply_preserves_source_rows_and_clamps_scores(self) -> None:
        source_rows = build_fixture_check_replay_rows(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            horizons=["H5"],
        )
        adjusted_rows = apply_reviewed_check_score_calibration_adjustments(
            source_rows,
            (
                reviewed_adjustment(category="A", slot=1, score_delta=-10.0),
                reviewed_adjustment(category="E", slot=6, score_delta=10.0),
            ),
        )
        source_by_slot = {row.category_slot: row for row in source_rows}
        adjusted_by_slot = {row.category_slot: row for row in adjusted_rows}

        self.assertEqual(source_by_slot["A1"].score, 1.2)
        self.assertEqual(adjusted_by_slot["A1"].score, 0.0)
        self.assertEqual(source_by_slot["E6"].score, 6.2)
        self.assertEqual(adjusted_by_slot["E6"].score, 10.0)

    def test_rejects_duplicate_adjustment_scopes(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            apply_reviewed_check_score_calibration_adjustments(
                build_fixture_check_replay_rows(
                    replay_date=date(2026, 5, 22),
                    symbols=["SPY"],
                    horizons=["H5"],
                ),
                (
                    reviewed_adjustment(),
                    reviewed_adjustment(score_delta=-0.1),
                ),
            )


def reviewed_adjustment(
    *,
    horizon: str = "H5",
    category: str = "B",
    slot: int = 3,
    score_delta: float = -0.25,
    calibration_review_run_id: str = "review-test",
    dry_run_simulation_run_id: str = "dry-run-test",
    approved_by: str = "m55-review",
    rationale: str = "Dry-run evidence showed B3 H5 running hot.",
) -> ReviewedCheckScoreCalibrationAdjustment:
    return ReviewedCheckScoreCalibrationAdjustment(
        horizon=horizon,
        category=category,
        slot=slot,
        score_delta=score_delta,
        calibration_review_run_id=calibration_review_run_id,
        dry_run_simulation_run_id=dry_run_simulation_run_id,
        approved_by=approved_by,
        rationale=rationale,
    )


if __name__ == "__main__":
    unittest.main()
