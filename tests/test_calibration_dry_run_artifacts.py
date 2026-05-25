from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from market_health.calibration.calibration_adjustment_artifacts import (
    CALIBRATION_ADJUSTMENT_CANDIDATES_CSV_FILENAME,
    CALIBRATION_DRY_RUN_COMPARISON_ROWS_CSV_FILENAME,
    CALIBRATION_DRY_RUN_MANIFEST_FILENAME,
    CALIBRATION_DRY_RUN_SIMULATION_ROWS_CSV_FILENAME,
    CALIBRATION_DRY_RUN_SQLITE_FILENAME,
    CALIBRATION_DRY_RUN_VALIDATION_SUMMARY_FILENAME,
    build_calibration_dry_run_validation_summary,
    calibration_dry_run_output_dir,
    write_calibration_dry_run_artifacts,
)
from market_health.calibration.calibration_adjustment_export import (
    CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE,
    CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE,
    CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE,
)
from market_health.calibration.calibration_adjustments import (
    build_calibration_dry_run_comparison_rows,
)
from tests.test_calibration_adjustments import glyph_candidate, named_check_candidate
from tests.test_calibration_dry_run_simulation import (
    apply_calibration_adjustment_candidates_dry_run,
    residual_row,
)


class CalibrationDryRunArtifactsTest(unittest.TestCase):
    def test_validation_summary_has_stable_shape_and_counts(self) -> None:
        candidates, simulation_rows, comparison_rows = dry_run_tables()

        summary = build_calibration_dry_run_validation_summary(
            candidates,
            simulation_rows,
            comparison_rows,
        )
        record = summary.to_record()

        self.assertEqual(record["candidate_count"], 2)
        self.assertEqual(record["simulation_row_count"], 2)
        self.assertEqual(record["comparison_row_count"], 1)
        self.assertEqual(record["unique_applied_candidate_count"], 2)
        self.assertEqual(record["symbols"], ["QQQ", "SPY"])
        self.assertEqual(record["symbol_count"], 2)
        self.assertEqual(record["horizons"], ["H1"])
        self.assertEqual(record["category_slots"], ["B4", "C2"])
        self.assertEqual(
            record["candidate_scope_counts"],
            {"glyph": 1, "named_check": 1},
        )
        self.assertEqual(record["comparison_group_counts"], {"overall": 1})
        self.assertEqual(record["residual_attribution_run_ids"], ["residual-test"])
        self.assertEqual(record["calibration_review_run_ids"], ["review-test"])
        self.assertEqual(record["dry_run_simulation_run_ids"], ["dry-run-test"])

    def test_output_dir_is_stable(self) -> None:
        self.assertEqual(
            calibration_dry_run_output_dir(Path("/tmp/out"), "dry-run-1"),
            Path("/tmp/out/calibration_dry_run/dry-run-1"),
        )

    def test_invalid_run_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            calibration_dry_run_output_dir(Path("/tmp/out"), "../bad")

    def test_write_calibration_dry_run_artifacts_outputs_files(self) -> None:
        candidates, simulation_rows, comparison_rows = dry_run_tables()

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = write_calibration_dry_run_artifacts(
                Path(tmpdir),
                candidates=candidates,
                simulation_rows=simulation_rows,
                comparison_rows=comparison_rows,
                dry_run_simulation_run_id="dry-run-test",
            )

            self.assertEqual(artifacts.candidate_count, 2)
            self.assertEqual(artifacts.simulation_row_count, 2)
            self.assertEqual(artifacts.comparison_row_count, 1)
            self.assertEqual(
                artifacts.candidates_csv_path.name,
                CALIBRATION_ADJUSTMENT_CANDIDATES_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.simulation_rows_csv_path.name,
                CALIBRATION_DRY_RUN_SIMULATION_ROWS_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.comparison_rows_csv_path.name,
                CALIBRATION_DRY_RUN_COMPARISON_ROWS_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.sqlite_path.name,
                CALIBRATION_DRY_RUN_SQLITE_FILENAME,
            )
            self.assertEqual(
                artifacts.validation_summary_path.name,
                CALIBRATION_DRY_RUN_VALIDATION_SUMMARY_FILENAME,
            )
            self.assertEqual(
                artifacts.manifest_path.name,
                CALIBRATION_DRY_RUN_MANIFEST_FILENAME,
            )

            with artifacts.candidates_csv_path.open(
                newline="",
                encoding="utf-8",
            ) as handle:
                candidate_rows = list(csv.DictReader(handle))
            with artifacts.simulation_rows_csv_path.open(
                newline="",
                encoding="utf-8",
            ) as handle:
                simulation_csv_rows = list(csv.DictReader(handle))
            with artifacts.comparison_rows_csv_path.open(
                newline="",
                encoding="utf-8",
            ) as handle:
                comparison_csv_rows = list(csv.DictReader(handle))

            validation_payload = json.loads(
                artifacts.validation_summary_path.read_text(encoding="utf-8")
            )
            manifest_payload = json.loads(
                artifacts.manifest_path.read_text(encoding="utf-8")
            )

            with sqlite3.connect(artifacts.sqlite_path) as connection:
                candidate_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE}"
                ).fetchone()[0]
                simulation_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE}"
                ).fetchone()[0]
                comparison_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE}"
                ).fetchone()[0]

        self.assertEqual(len(candidate_rows), artifacts.candidate_count)
        self.assertEqual(len(simulation_csv_rows), artifacts.simulation_row_count)
        self.assertEqual(len(comparison_csv_rows), artifacts.comparison_row_count)
        self.assertEqual(candidate_count, artifacts.candidate_count)
        self.assertEqual(simulation_count, artifacts.simulation_row_count)
        self.assertEqual(comparison_count, artifacts.comparison_row_count)
        self.assertEqual(validation_payload["candidate_count"], 2)
        self.assertEqual(manifest_payload["candidate_count"], 2)
        self.assertEqual(manifest_payload["simulation_row_count"], 2)


def dry_run_tables():
    candidates = (
        glyph_candidate(
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
    )
    residual_rows = (
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
            named_check="breadth_confirmed",
            forecast_score=7.5,
            realized_current_score=8.0,
            residual=-0.5,
            residual_direction="cold",
        ),
    )
    simulation_rows = apply_calibration_adjustment_candidates_dry_run(
        residual_rows,
        candidates,
        dry_run_simulation_run_id="dry-run-test",
    )
    comparison_rows = build_calibration_dry_run_comparison_rows(
        simulation_rows,
        groupings=("overall",),
    )
    return candidates, simulation_rows, comparison_rows


if __name__ == "__main__":
    unittest.main()
