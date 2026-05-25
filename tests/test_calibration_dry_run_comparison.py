from __future__ import annotations

import unittest

from market_health.calibration.calibration_adjustments import (
    CALIBRATION_DRY_RUN_COMPARISON_SCHEMA_VERSION,
    build_calibration_dry_run_comparison_rows,
)
from tests.test_calibration_adjustments import glyph_candidate, named_check_candidate
from tests.test_calibration_dry_run_simulation import residual_row
from market_health.calibration.calibration_adjustments import (
    apply_calibration_adjustment_candidates_dry_run,
)


class CalibrationDryRunComparisonTest(unittest.TestCase):
    def test_builds_overall_comparison_metrics(self) -> None:
        comparison_rows = build_calibration_dry_run_comparison_rows(
            simulation_rows(),
            groupings=("overall",),
        )

        self.assertEqual(len(comparison_rows), 1)
        row = comparison_rows[0]

        self.assertEqual(
            row.schema_version, CALIBRATION_DRY_RUN_COMPARISON_SCHEMA_VERSION
        )
        self.assertEqual(row.group_name, "overall")
        self.assertEqual(row.group_value, "all")
        self.assertEqual(row.observation_count, 3)
        self.assertEqual(row.baseline_mean_residual, 0.16666667)
        self.assertEqual(row.simulated_mean_residual, 0.25)
        self.assertEqual(row.baseline_mean_abs_residual, 0.5)
        self.assertEqual(row.simulated_mean_abs_residual, 0.41666667)
        self.assertEqual(row.mean_abs_residual_delta, -0.08333333)
        self.assertEqual(row.mean_abs_residual_improvement, 0.08333333)
        self.assertEqual(row.improved_count, 2)
        self.assertEqual(row.worsened_count, 1)
        self.assertEqual(row.unchanged_count, 0)
        self.assertEqual(row.baseline_hot_count, 2)
        self.assertEqual(row.baseline_cold_count, 1)
        self.assertEqual(row.baseline_neutral_count, 0)
        self.assertEqual(row.simulated_hot_count, 2)
        self.assertEqual(row.simulated_cold_count, 1)
        self.assertEqual(row.simulated_neutral_count, 0)
        self.assertEqual(row.unique_applied_candidate_count, 3)
        self.assertEqual(row.residual_attribution_run_id, "residual-test")
        self.assertEqual(row.calibration_review_run_id, "review-test")
        self.assertEqual(row.dry_run_simulation_run_id, "dry-run-test")
        self.assertTrue(row.dry_run_only)

    def test_record_has_stable_shape(self) -> None:
        record = build_calibration_dry_run_comparison_rows(
            simulation_rows()[:1],
            groupings=("overall",),
        )[0].to_record()

        self.assertEqual(
            list(record),
            [
                "schema_version",
                "group_name",
                "group_value",
                "horizon",
                "category",
                "slot",
                "category_slot",
                "glyph",
                "named_check",
                "observation_count",
                "baseline_mean_residual",
                "simulated_mean_residual",
                "baseline_mean_abs_residual",
                "simulated_mean_abs_residual",
                "mean_abs_residual_delta",
                "mean_abs_residual_improvement",
                "improved_count",
                "worsened_count",
                "unchanged_count",
                "baseline_hot_count",
                "baseline_cold_count",
                "baseline_neutral_count",
                "simulated_hot_count",
                "simulated_cold_count",
                "simulated_neutral_count",
                "unique_applied_candidate_count",
                "applied_candidate_ids",
                "residual_attribution_run_id",
                "calibration_review_run_id",
                "dry_run_simulation_run_id",
                "dry_run_only",
            ],
        )
        self.assertEqual(
            record["schema_version"], CALIBRATION_DRY_RUN_COMPARISON_SCHEMA_VERSION
        )
        self.assertIn(
            "calibration-adjustment-candidate:", record["applied_candidate_ids"]
        )

    def test_builds_default_groupings_with_context(self) -> None:
        comparison_rows = build_calibration_dry_run_comparison_rows(simulation_rows())

        keys = [(row.group_name, row.group_value) for row in comparison_rows]

        self.assertEqual(
            keys,
            [
                ("overall", "all"),
                ("horizon", "H1"),
                ("category_slot", "H1:B4"),
                ("category_slot", "H1:C2"),
                ("category_slot", "H1:D3"),
                ("glyph", "H1:B4:+"),
                ("glyph", "H1:C2:-"),
                ("glyph", "H1:D3:F"),
                ("named_check", "H1:breadth_confirmed"),
                ("named_check", "H1:risk_filter"),
                ("named_check", "H1:trend_confirmed"),
            ],
        )

        category_slot = next(
            row
            for row in comparison_rows
            if row.group_name == "category_slot" and row.group_value == "H1:C2"
        )
        self.assertEqual(category_slot.horizon, "H1")
        self.assertEqual(category_slot.category, "C")
        self.assertEqual(category_slot.slot, 2)
        self.assertEqual(category_slot.category_slot, "C2")
        self.assertIsNone(category_slot.glyph)
        self.assertIsNone(category_slot.named_check)

        named_check = next(
            row
            for row in comparison_rows
            if row.group_name == "named_check"
            and row.group_value == "H1:trend_confirmed"
        )
        self.assertEqual(named_check.horizon, "H1")
        self.assertEqual(named_check.named_check, "trend_confirmed")
        self.assertIsNone(named_check.category)

    def test_empty_input_returns_empty_rows(self) -> None:
        self.assertEqual(build_calibration_dry_run_comparison_rows(()), ())

    def test_rejects_invalid_groupings(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            build_calibration_dry_run_comparison_rows(
                simulation_rows(),
                groupings=(),
            )

        with self.assertRaisesRegex(ValueError, "unique"):
            build_calibration_dry_run_comparison_rows(
                simulation_rows(),
                groupings=("overall", "overall"),
            )

        with self.assertRaisesRegex(ValueError, "unsupported"):
            build_calibration_dry_run_comparison_rows(
                simulation_rows(),
                groupings=("bad",),
            )

    def test_rejects_mixed_run_ids_inside_comparison_bucket(self) -> None:
        mixed_rows = (
            *simulation_rows(dry_run_simulation_run_id="dry-run-a")[:1],
            *simulation_rows(dry_run_simulation_run_id="dry-run-b")[:1],
        )

        with self.assertRaisesRegex(ValueError, "dry_run_simulation_run_id"):
            build_calibration_dry_run_comparison_rows(
                mixed_rows,
                groupings=("overall",),
            )


def simulation_rows(
    *,
    dry_run_simulation_run_id: str = "dry-run-test",
):
    rows = (
        residual_row(
            symbol="SPY",
            category="B",
            slot=4,
            glyph="+",
            named_check="trend_confirmed",
            forecast_score=8.5,
            realized_current_score=8.0,
            residual=0.5,
            residual_direction="hot",
        ),
        residual_row(
            symbol="QQQ",
            category="C",
            slot=2,
            glyph="-",
            named_check="breadth_confirmed",
            forecast_score=7.5,
            realized_current_score=8.0,
            residual=-0.5,
            residual_direction="cold",
        ),
        residual_row(
            symbol="IWM",
            category="D",
            slot=3,
            glyph="F",
            named_check="risk_filter",
            forecast_score=8.5,
            realized_current_score=8.0,
            residual=0.5,
            residual_direction="hot",
        ),
    )
    candidates = (
        glyph_candidate(
            category="B",
            slot=4,
            glyph="+",
            score_delta=-0.25,
            mean_residual=0.25,
            calibration_review_run_id="review-test",
        ),
        named_check_candidate(
            horizon="H1",
            named_check="breadth_confirmed",
            category="C",
            slot=2,
            glyph="-",
            review_classification="cold",
            adjustment_direction="increase_score",
            score_delta=0.25,
            mean_residual=-0.25,
            calibration_review_run_id="review-test",
        ),
        named_check_candidate(
            horizon="H1",
            named_check="risk_filter",
            category="D",
            slot=3,
            glyph="F",
            review_classification="cold",
            adjustment_direction="increase_score",
            score_delta=0.25,
            mean_residual=-0.25,
            calibration_review_run_id="review-test",
        ),
    )

    return apply_calibration_adjustment_candidates_dry_run(
        rows,
        candidates,
        dry_run_simulation_run_id=dry_run_simulation_run_id,
    )


if __name__ == "__main__":
    unittest.main()
