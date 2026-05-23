from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.residual_attribution_artifacts import (
    RESIDUAL_ATTRIBUTION_MANIFEST_FILENAME,
    RESIDUAL_ATTRIBUTION_ROWS_CSV_FILENAME,
    RESIDUAL_ATTRIBUTION_SQLITE_FILENAME,
    RESIDUAL_ATTRIBUTION_SUMMARIES_CSV_FILENAME,
    RESIDUAL_ATTRIBUTION_VALIDATION_SUMMARY_FILENAME,
    build_residual_attribution_validation_summary,
    residual_attribution_output_dir,
    write_residual_attribution_artifacts,
)
from market_health.calibration.residual_attribution_export import (
    RESIDUAL_ATTRIBUTION_ROWS_TABLE,
    RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE,
)
from market_health.calibration.residuals import (
    ResidualAttributionRow,
    ResidualAttributionSummaryRow,
)


class ResidualAttributionArtifactsTest(unittest.TestCase):
    def test_validation_summary_has_stable_shape_and_counts(self) -> None:
        summary = build_residual_attribution_validation_summary(
            (
                row(symbol="SPY", residual=0.5, residual_direction="hot"),
                row(
                    symbol="QQQ",
                    forecast_score=7.25,
                    realized_current_score=7.5,
                    residual=-0.25,
                    residual_direction="cold",
                ),
            ),
            (summary_row(),),
        )

        record = summary.to_record()

        self.assertEqual(record["observation_count"], 2)
        self.assertEqual(record["summary_count"], 1)
        self.assertEqual(record["replay_dates"], ["2026-05-20"])
        self.assertEqual(record["symbols"], ["QQQ", "SPY"])
        self.assertEqual(record["horizons"], ["H1"])
        self.assertEqual(record["categories"], ["B"])
        self.assertEqual(record["category_slots"], ["B4"])
        self.assertEqual(
            record["residual_direction_counts"],
            {"hot": 1, "cold": 1, "neutral": 0},
        )
        self.assertEqual(record["residual_attribution_run_ids"], ["m52-test"])
        self.assertEqual(record["dataset_run_ids"], ["dataset-test"])

    def test_output_dir_is_stable(self) -> None:
        self.assertEqual(
            residual_attribution_output_dir(Path("/tmp/out"), "run-1"),
            Path("/tmp/out/residual_attribution/run-1"),
        )

    def test_invalid_run_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            residual_attribution_output_dir(Path("/tmp/out"), "../bad")

    def test_write_residual_attribution_artifacts_outputs_files(self) -> None:
        rows = (
            row(symbol="SPY", residual=0.5, residual_direction="hot"),
            row(
                symbol="QQQ",
                forecast_score=7.25,
                realized_current_score=7.5,
                residual=-0.25,
                residual_direction="cold",
            ),
        )
        summaries = (summary_row(),)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = write_residual_attribution_artifacts(
                Path(tmpdir),
                rows=rows,
                summaries=summaries,
                residual_attribution_run_id="m52-test",
            )

            self.assertEqual(artifacts.observation_count, 2)
            self.assertEqual(artifacts.summary_count, 1)
            self.assertEqual(
                artifacts.rows_csv_path.name, RESIDUAL_ATTRIBUTION_ROWS_CSV_FILENAME
            )
            self.assertEqual(
                artifacts.summaries_csv_path.name,
                RESIDUAL_ATTRIBUTION_SUMMARIES_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.sqlite_path.name, RESIDUAL_ATTRIBUTION_SQLITE_FILENAME
            )
            self.assertEqual(
                artifacts.validation_summary_path.name,
                RESIDUAL_ATTRIBUTION_VALIDATION_SUMMARY_FILENAME,
            )
            self.assertEqual(
                artifacts.manifest_path.name, RESIDUAL_ATTRIBUTION_MANIFEST_FILENAME
            )

            with artifacts.rows_csv_path.open(newline="", encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(len(csv_rows), 2)

            validation_payload = json.loads(
                artifacts.validation_summary_path.read_text(encoding="utf-8")
            )
            manifest_payload = json.loads(
                artifacts.manifest_path.read_text(encoding="utf-8")
            )

            self.assertEqual(validation_payload["observation_count"], 2)
            self.assertEqual(manifest_payload["observation_count"], 2)
            self.assertEqual(manifest_payload["summary_count"], 1)

            with sqlite3.connect(artifacts.sqlite_path) as connection:
                row_count = connection.execute(
                    f"SELECT COUNT(*) FROM {RESIDUAL_ATTRIBUTION_ROWS_TABLE}"
                ).fetchone()[0]
                summary_count = connection.execute(
                    f"SELECT COUNT(*) FROM {RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE}"
                ).fetchone()[0]

            self.assertEqual(row_count, 2)
            self.assertEqual(summary_count, 1)


def row(
    *,
    symbol: str = "SPY",
    forecast_score: float = 8.5,
    realized_current_score: float = 8.0,
    residual: float = 0.5,
    residual_direction: str = "hot",
) -> ResidualAttributionRow:
    return ResidualAttributionRow(
        replay_date=date(2026, 5, 20),
        symbol=symbol,
        horizon="H1",
        target_date=date(2026, 5, 21),
        forecast_score=forecast_score,
        realized_current_score=realized_current_score,
        residual=residual,
        residual_direction=residual_direction,
        realized_return=0.03,
        category="B",
        slot=4,
        glyph="+",
        named_check="trend_confirmed",
        check_score=4.1,
        replayability_class="replayable",
        measurement_status="measured",
        source_module="fixture.module",
        function_name="check_b4",
        audit_token="single-date-asof:2026-05-20:SPY:1:100.0000",
        dataset_run_id="dataset-test",
        residual_attribution_run_id="m52-test",
    )


def summary_row() -> ResidualAttributionSummaryRow:
    return ResidualAttributionSummaryRow(
        group_name="horizon",
        group_value="H1",
        horizon="H1",
        observation_count=2,
        mean_residual=0.125,
        mean_abs_residual=0.375,
        hot_count=1,
        cold_count=1,
        neutral_count=0,
        residual_attribution_run_id="m52-test",
    )


if __name__ == "__main__":
    unittest.main()
