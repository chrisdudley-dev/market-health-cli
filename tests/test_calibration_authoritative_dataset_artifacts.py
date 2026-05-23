from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.authoritative_dataset import (
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_MISSING,
    REALIZED_OUTCOME_NOT_APPLICABLE,
    AuthoritativeReplayDatasetRow,
)
from market_health.calibration.authoritative_dataset_artifacts import (
    AUTHORITATIVE_DATASET_ARTIFACT_SCHEMA_VERSION,
    AUTHORITATIVE_DATASET_CSV_FILENAME,
    AUTHORITATIVE_DATASET_MANIFEST_FILENAME,
    AUTHORITATIVE_DATASET_SQLITE_FILENAME,
    AUTHORITATIVE_DATASET_VALIDATION_SUMMARY_FILENAME,
    build_authoritative_dataset_validation_summary,
    write_authoritative_dataset_artifacts,
)
from market_health.calibration.authoritative_dataset_export import (
    AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE,
)
from market_health.calibration.check_output import MEASUREMENT_MEASURED


class AuthoritativeDatasetArtifactsTest(unittest.TestCase):
    def test_validation_summary_has_stable_shape_and_counts(self) -> None:
        summary = build_authoritative_dataset_validation_summary(
            [
                _row(horizon="C"),
                _row(horizon="H1", status=REALIZED_OUTCOME_AVAILABLE),
                _row(horizon="H5", status=REALIZED_OUTCOME_MISSING),
            ]
        )

        self.assertEqual(summary.row_count, 3)
        self.assertEqual(summary.replay_date_count, 1)
        self.assertEqual(summary.symbol_count, 1)
        self.assertEqual(summary.replay_dates, (date(2026, 5, 20),))
        self.assertEqual(summary.symbols, ("SPY",))
        self.assertEqual(summary.horizons, ("C", "H1", "H5"))
        self.assertEqual(
            summary.realized_outcome_status_counts,
            {
                REALIZED_OUTCOME_AVAILABLE: 1,
                REALIZED_OUTCOME_MISSING: 1,
                REALIZED_OUTCOME_NOT_APPLICABLE: 1,
            },
        )
        self.assertEqual(summary.dataset_run_ids, ("dataset-test",))
        self.assertEqual(
            summary.schema_versions,
            ("calibration_authoritative_replay_dataset.v1",),
        )

    def test_write_authoritative_dataset_artifacts_outputs_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_authoritative_dataset_artifacts(
                output_root=Path(tmp),
                rows=[
                    _row(horizon="H1", status=REALIZED_OUTCOME_AVAILABLE),
                    _row(horizon="C"),
                ],
                dataset_run_id="dataset-test",
            )

            self.assertEqual(
                artifacts.output_dir,
                Path(tmp) / "authoritative_dataset" / "dataset-test",
            )
            self.assertEqual(
                artifacts.dataset_csv_path.name,
                AUTHORITATIVE_DATASET_CSV_FILENAME,
            )
            self.assertEqual(
                artifacts.dataset_sqlite_path.name,
                AUTHORITATIVE_DATASET_SQLITE_FILENAME,
            )
            self.assertEqual(
                artifacts.validation_summary_path.name,
                AUTHORITATIVE_DATASET_VALIDATION_SUMMARY_FILENAME,
            )
            self.assertEqual(
                artifacts.manifest_path.name,
                AUTHORITATIVE_DATASET_MANIFEST_FILENAME,
            )

            with artifacts.dataset_csv_path.open(
                newline="", encoding="utf-8"
            ) as handle:
                csv_rows = list(csv.DictReader(handle))

            with sqlite3.connect(artifacts.dataset_sqlite_path) as conn:
                sqlite_count = conn.execute(
                    f"SELECT COUNT(*) FROM {AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE}"
                ).fetchone()[0]

            summary_payload = json.loads(
                artifacts.validation_summary_path.read_text(encoding="utf-8")
            )
            manifest_payload = json.loads(
                artifacts.manifest_path.read_text(encoding="utf-8")
            )

        self.assertEqual(len(csv_rows), 2)
        self.assertEqual(sqlite_count, 2)
        self.assertEqual(summary_payload["row_count"], 2)
        self.assertEqual(
            manifest_payload["schema_version"],
            AUTHORITATIVE_DATASET_ARTIFACT_SCHEMA_VERSION,
        )
        self.assertEqual(manifest_payload["artifacts"]["row_count"], 2)

    def test_invalid_dataset_run_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "dataset_run_id"):
                write_authoritative_dataset_artifacts(
                    output_root=Path(tmp),
                    rows=[],
                    dataset_run_id="bad run id",
                )


def _row(
    *,
    horizon: str = "C",
    status: str = REALIZED_OUTCOME_NOT_APPLICABLE,
) -> AuthoritativeReplayDatasetRow:
    is_available = status == REALIZED_OUTCOME_AVAILABLE
    is_missing = status == REALIZED_OUTCOME_MISSING

    return AuthoritativeReplayDatasetRow(
        replay_date=date(2026, 5, 20),
        symbol="SPY",
        current_score=5.1,
        h1_score=5.2,
        h5_score=5.3,
        blend_score=5.2,
        state="YELLOW",
        horizon=horizon,
        target_date=date(2026, 5, 21) if is_available or is_missing else None,
        realized_current_score=8.0 if is_available else None,
        realized_return=0.03 if is_available else None,
        realized_outcome_status=status,
        category="A",
        slot={"C": 1, "H1": 2, "H5": 3}[horizon],
        glyph=f"{horizon.lower()[0]}1",
        named_check=f"Check {horizon}",
        check_score=1.0,
        replayability_class="replayable",
        measurement_status=MEASUREMENT_MEASURED,
        source_module="fixture.module",
        function_name=f"check_{horizon.lower()}",
        audit_token="single-date-asof:2026-05-20:SPY:1:100.0000",
        dataset_run_id="dataset-test",
    )


if __name__ == "__main__":
    unittest.main()
