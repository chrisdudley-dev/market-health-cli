from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_adjustments import (
    CALIBRATION_DRY_RUN_SIMULATION_SCHEMA_VERSION,
    apply_calibration_adjustment_candidates_dry_run,
)
from market_health.calibration.residuals import ResidualAttributionRow

from tests.test_calibration_adjustments import glyph_candidate, named_check_candidate


class CalibrationDryRunSimulationTest(unittest.TestCase):
    def test_applies_glyph_and_named_check_candidates_additively(self) -> None:
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
        )
        candidates = (
            glyph_candidate(
                score_delta=-0.25,
                mean_residual=0.25,
                calibration_review_run_id="review-test",
            ),
            named_check_candidate(
                horizon="H1",
                named_check="trend_confirmed",
                review_classification="hot",
                adjustment_direction="decrease_score",
                score_delta=-0.1,
                mean_residual=0.1,
                calibration_review_run_id="review-test",
            ),
        )

        simulation_rows = apply_calibration_adjustment_candidates_dry_run(
            rows,
            candidates,
            dry_run_simulation_run_id="dry-run-test",
        )

        self.assertEqual(len(simulation_rows), 1)
        row = simulation_rows[0]
        self.assertEqual(
            row.schema_version, CALIBRATION_DRY_RUN_SIMULATION_SCHEMA_VERSION
        )
        self.assertEqual(row.baseline_forecast_score, 8.5)
        self.assertEqual(row.simulated_forecast_score, 8.15)
        self.assertEqual(row.realized_current_score, 8.0)
        self.assertEqual(row.baseline_residual, 0.5)
        self.assertEqual(row.simulated_residual, 0.15)
        self.assertEqual(row.baseline_residual_direction, "hot")
        self.assertEqual(row.simulated_residual_direction, "hot")
        self.assertEqual(row.applied_score_delta, -0.35)
        self.assertEqual(row.applied_candidate_count, 2)
        self.assertEqual(
            row.applied_candidate_ids,
            tuple(sorted(row.applied_candidate_ids)),
        )
        self.assertEqual(row.residual_attribution_run_id, "residual-test")
        self.assertEqual(row.calibration_review_run_id, "review-test")
        self.assertEqual(row.dry_run_simulation_run_id, "dry-run-test")
        self.assertTrue(row.dry_run_only)

    def test_record_has_stable_shape(self) -> None:
        simulation_row = apply_calibration_adjustment_candidates_dry_run(
            (residual_row(),),
            (
                glyph_candidate(
                    calibration_review_run_id="review-test",
                ),
            ),
            dry_run_simulation_run_id="dry-run-test",
        )[0]

        record = simulation_row.to_record()

        self.assertEqual(
            list(record),
            [
                "schema_version",
                "replay_date",
                "symbol",
                "horizon",
                "target_date",
                "category",
                "slot",
                "category_slot",
                "glyph",
                "named_check",
                "baseline_forecast_score",
                "simulated_forecast_score",
                "realized_current_score",
                "baseline_residual",
                "simulated_residual",
                "baseline_residual_direction",
                "simulated_residual_direction",
                "applied_score_delta",
                "applied_candidate_count",
                "applied_candidate_ids",
                "residual_attribution_run_id",
                "calibration_review_run_id",
                "dry_run_simulation_run_id",
                "source_residual_schema_version",
                "dry_run_only",
            ],
        )
        self.assertEqual(record["replay_date"], "2026-05-20")
        self.assertEqual(record["symbol"], "SPY")
        self.assertEqual(record["category_slot"], "B4")
        self.assertIn(
            "calibration-adjustment-candidate:", record["applied_candidate_ids"]
        )

    def test_named_check_candidate_can_apply_without_category_context(self) -> None:
        simulation_rows = apply_calibration_adjustment_candidates_dry_run(
            (
                residual_row(
                    symbol="SPY",
                    category="B",
                    slot=4,
                    glyph="+",
                    named_check="trend_confirmed",
                ),
                residual_row(
                    symbol="QQQ",
                    category="C",
                    slot=2,
                    glyph="-",
                    named_check="trend_confirmed",
                ),
            ),
            (
                named_check_candidate(
                    horizon="H1",
                    named_check="trend_confirmed",
                    category=None,
                    slot=None,
                    glyph=None,
                    review_classification="hot",
                    adjustment_direction="decrease_score",
                    score_delta=-0.2,
                    mean_residual=0.2,
                    calibration_review_run_id="review-test",
                ),
            ),
            dry_run_simulation_run_id="dry-run-test",
        )

        self.assertEqual(len(simulation_rows), 2)
        self.assertEqual(
            [(row.symbol, row.applied_score_delta) for row in simulation_rows],
            [("QQQ", -0.2), ("SPY", -0.2)],
        )

    def test_skips_rows_without_matching_candidates(self) -> None:
        simulation_rows = apply_calibration_adjustment_candidates_dry_run(
            (residual_row(category="C", slot=2, glyph="-"),),
            (
                glyph_candidate(
                    category="B",
                    slot=4,
                    glyph="+",
                    calibration_review_run_id="review-test",
                ),
            ),
        )

        self.assertEqual(simulation_rows, ())

    def test_clamps_simulated_score_without_mutating_source_row(self) -> None:
        source_row = residual_row(
            forecast_score=9.9,
            realized_current_score=9.5,
            residual=0.4,
            residual_direction="hot",
        )
        candidate = named_check_candidate(
            horizon="H1",
            review_classification="cold",
            adjustment_direction="increase_score",
            score_delta=0.5,
            mean_residual=-0.5,
            calibration_review_run_id="review-test",
        )

        simulation_row = apply_calibration_adjustment_candidates_dry_run(
            (source_row,),
            (candidate,),
        )[0]

        self.assertEqual(simulation_row.simulated_forecast_score, 10.0)
        self.assertEqual(simulation_row.applied_score_delta, 0.1)
        self.assertEqual(source_row.forecast_score, 9.9)
        self.assertEqual(candidate.score_delta, 0.5)

    def test_rejects_candidates_with_mixed_review_run_ids_for_same_row(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibration_review_run_id"):
            apply_calibration_adjustment_candidates_dry_run(
                (residual_row(),),
                (
                    glyph_candidate(calibration_review_run_id="review-a"),
                    named_check_candidate(
                        horizon="H1",
                        review_classification="hot",
                        adjustment_direction="decrease_score",
                        score_delta=-0.1,
                        mean_residual=0.1,
                        calibration_review_run_id="review-b",
                    ),
                ),
            )

    def test_rejects_invalid_simulation_run_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "dry_run_simulation_run_id"):
            apply_calibration_adjustment_candidates_dry_run(
                (),
                (),
                dry_run_simulation_run_id=" ",
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
    residual_attribution_run_id: str = "residual-test",
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
