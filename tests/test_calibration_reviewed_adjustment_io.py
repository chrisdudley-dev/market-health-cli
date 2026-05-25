from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from market_health.calibration.check_output import (
    REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION,
    ReviewedCheckScoreCalibrationAdjustment,
)
from market_health.calibration.reviewed_adjustment_io import (
    read_reviewed_check_score_adjustments_json,
    reviewed_check_score_adjustments_payload,
    reviewed_check_score_adjustments_to_records,
    write_reviewed_check_score_adjustments_json,
)


class ReviewedAdjustmentIoTest(unittest.TestCase):
    def test_records_and_payload_have_stable_shape(self) -> None:
        adjustments = (reviewed_adjustment(),)

        records = reviewed_check_score_adjustments_to_records(adjustments)
        payload = reviewed_check_score_adjustments_payload(adjustments)

        self.assertEqual(records[0]["category_slot"], "B3")
        self.assertEqual(
            payload["schema_version"],
            REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION,
        )
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["rows"], records)

    def test_write_and_read_round_trip(self) -> None:
        adjustments = (
            reviewed_adjustment(),
            reviewed_adjustment(horizon="H1", category="C", slot=5, score_delta=0.15),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "reviewed_check_score_adjustments.json"
            written_path = write_reviewed_check_score_adjustments_json(
                path,
                adjustments,
            )
            loaded = read_reviewed_check_score_adjustments_json(written_path)

        self.assertEqual(loaded, adjustments)
        self.assertEqual(loaded[0].category_slot, "B3")
        self.assertEqual(loaded[1].category_slot, "C5")

    def test_reader_rejects_bad_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "wrong",
                        "row_count": 0,
                        "rows": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "schema version"):
                read_reviewed_check_score_adjustments_json(path)

    def test_reader_rejects_row_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION,
                        "row_count": 2,
                        "rows": [reviewed_adjustment().to_record()],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "row_count"):
                read_reviewed_check_score_adjustments_json(path)

    def test_reader_rejects_duplicate_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "duplicate.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION,
                        "row_count": 2,
                        "rows": [
                            reviewed_adjustment().to_record(),
                            reviewed_adjustment(score_delta=-0.1).to_record(),
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate"):
                read_reviewed_check_score_adjustments_json(path)


def reviewed_adjustment(
    *,
    horizon: str = "H5",
    category: str = "B",
    slot: int = 3,
    score_delta: float = -0.25,
) -> ReviewedCheckScoreCalibrationAdjustment:
    return ReviewedCheckScoreCalibrationAdjustment(
        horizon=horizon,
        category=category,
        slot=slot,
        score_delta=score_delta,
        calibration_review_run_id="review-test",
        dry_run_simulation_run_id="dry-run-test",
        approved_by="m55-review",
        rationale="Dry-run evidence supported a reviewed adjustment.",
    )


if __name__ == "__main__":
    unittest.main()
