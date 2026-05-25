from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.calibration_review import (
    CalibrationReviewWindow,
    build_windowed_calibration_review_tables,
)
from market_health.calibration.calibration_review_artifacts import (
    CALIBRATION_GLYPH_REVIEW_EXAMPLES_CSV_FILENAME,
    CALIBRATION_GLYPH_REVIEW_ROWS_CSV_FILENAME,
    CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_CSV_FILENAME,
    CALIBRATION_NAMED_CHECK_REVIEW_ROWS_CSV_FILENAME,
    CALIBRATION_REVIEW_MANIFEST_FILENAME,
    CALIBRATION_REVIEW_SQLITE_FILENAME,
    CALIBRATION_REVIEW_VALIDATION_SUMMARY_FILENAME,
    CALIBRATION_REVIEW_WINDOW_SUMMARIES_CSV_FILENAME,
    build_calibration_review_validation_summary,
    calibration_review_output_dir,
    write_calibration_review_artifacts,
)
from market_health.calibration.calibration_review_export import (
    CALIBRATION_GLYPH_REVIEW_EXAMPLES_TABLE,
    CALIBRATION_GLYPH_REVIEW_ROWS_TABLE,
    CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_TABLE,
    CALIBRATION_NAMED_CHECK_REVIEW_ROWS_TABLE,
    CALIBRATION_REVIEW_WINDOW_SUMMARIES_TABLE,
)
from market_health.calibration.residuals import ResidualAttributionRow


class CalibrationReviewArtifactsTest(unittest.TestCase):
    def test_validation_summary_has_stable_counts(self) -> None:
        windowed_tables = build_windowed_calibration_review_tables(
            residual_rows(),
            windows=(CalibrationReviewWindow("full"),),
            min_observation_count=1,
            max_examples_per_group=1,
        )

        summary = build_calibration_review_validation_summary(windowed_tables)
        record = summary.to_record()

        self.assertEqual(record["window_count"], 1)
        self.assertEqual(record["residual_observation_count"], 3)
        self.assertEqual(record["glyph_review_row_count"], 2)
        self.assertEqual(record["named_check_review_row_count"], 2)
        self.assertEqual(record["glyph_example_row_count"], 2)
        self.assertEqual(record["named_check_example_row_count"], 2)
        self.assertEqual(record["window_labels"], ["full"])
        self.assertEqual(record["residual_attribution_run_ids"], ["m53-test"])
        self.assertEqual(
            record["review_classification_counts"],
            {"hot": 2, "cold": 2, "inconclusive": 0},
        )

    def test_output_dir_is_stable(self) -> None:
        self.assertEqual(
            calibration_review_output_dir(Path("/tmp/out"), "run-1"),
            Path("/tmp/out/calibration_review/run-1"),
        )

    def test_invalid_run_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            calibration_review_output_dir(Path("/tmp/out"), "../bad")

    def test_write_calibration_review_artifacts_outputs_files(self) -> None:
        windowed_tables = build_windowed_calibration_review_tables(
            residual_rows(),
            windows=(
                CalibrationReviewWindow("full"),
                CalibrationReviewWindow(
                    "1d",
                    start_date=date(2026, 5, 20),
                    end_date=date(2026, 5, 20),
                ),
            ),
            min_observation_count=1,
            max_examples_per_group=1,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = write_calibration_review_artifacts(
                Path(tmpdir),
                windowed_tables=windowed_tables,
                calibration_review_run_id="m53-test",
            )

            self.assertEqual(artifacts.window_count, 2)
            self.assertEqual(artifacts.residual_observation_count, 6)
            self.assertEqual(
                artifacts.glyph_rows_csv_path.name,
                CALIBRATION_GLYPH_REVIEW_ROWS_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.named_check_rows_csv_path.name,
                CALIBRATION_NAMED_CHECK_REVIEW_ROWS_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.glyph_examples_csv_path.name,
                CALIBRATION_GLYPH_REVIEW_EXAMPLES_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.named_check_examples_csv_path.name,
                CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.window_summaries_csv_path.name,
                CALIBRATION_REVIEW_WINDOW_SUMMARIES_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.sqlite_path.name, CALIBRATION_REVIEW_SQLITE_FILENAME
            )
            self.assertEqual(
                artifacts.validation_summary_path.name,
                CALIBRATION_REVIEW_VALIDATION_SUMMARY_FILENAME,
            )
            self.assertEqual(
                artifacts.manifest_path.name, CALIBRATION_REVIEW_MANIFEST_FILENAME
            )

            with artifacts.glyph_rows_csv_path.open(
                newline="", encoding="utf-8"
            ) as handle:
                glyph_rows = list(csv.DictReader(handle))
            with artifacts.named_check_rows_csv_path.open(
                newline="",
                encoding="utf-8",
            ) as handle:
                named_check_rows = list(csv.DictReader(handle))
            with artifacts.window_summaries_csv_path.open(
                newline="",
                encoding="utf-8",
            ) as handle:
                window_rows = list(csv.DictReader(handle))

            validation_payload = json.loads(
                artifacts.validation_summary_path.read_text(encoding="utf-8")
            )
            manifest_payload = json.loads(
                artifacts.manifest_path.read_text(encoding="utf-8")
            )

            with sqlite3.connect(artifacts.sqlite_path) as connection:
                glyph_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_GLYPH_REVIEW_ROWS_TABLE}"
                ).fetchone()[0]
                named_check_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_NAMED_CHECK_REVIEW_ROWS_TABLE}"
                ).fetchone()[0]
                glyph_example_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_GLYPH_REVIEW_EXAMPLES_TABLE}"
                ).fetchone()[0]
                named_check_example_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_TABLE}"
                ).fetchone()[0]
                window_count = connection.execute(
                    f"SELECT COUNT(*) FROM {CALIBRATION_REVIEW_WINDOW_SUMMARIES_TABLE}"
                ).fetchone()[0]

        self.assertEqual(len(glyph_rows), artifacts.glyph_review_row_count)
        self.assertEqual(len(named_check_rows), artifacts.named_check_review_row_count)
        self.assertEqual(len(window_rows), artifacts.window_count)
        self.assertEqual(glyph_count, artifacts.glyph_review_row_count)
        self.assertEqual(named_check_count, artifacts.named_check_review_row_count)
        self.assertEqual(glyph_example_count, artifacts.glyph_example_row_count)
        self.assertEqual(
            named_check_example_count,
            artifacts.named_check_example_row_count,
        )
        self.assertEqual(window_count, artifacts.window_count)
        self.assertEqual(validation_payload["window_count"], 2)
        self.assertEqual(manifest_payload["window_count"], 2)
        self.assertEqual(manifest_payload["residual_observation_count"], 6)


def residual_rows() -> tuple[ResidualAttributionRow, ...]:
    return (
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
            category="C",
            slot=2,
            glyph="-",
            named_check="breadth_confirmed",
            forecast_score=7.25,
            realized_current_score=8.0,
            residual=-0.75,
            residual_direction="cold",
        ),
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
