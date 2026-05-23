from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.authoritative_dataset import (
    AUTHORITATIVE_REPLAY_DATASET_COLUMNS,
    AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION,
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_MISSING,
    REALIZED_OUTCOME_NOT_APPLICABLE,
    AuthoritativeReplayDatasetRow,
)
from market_health.calibration.check_output import (
    CHECK_REPLAY_ROW_SCHEMA_VERSION,
    MEASUREMENT_MEASURED,
)
from market_health.calibration.range_runner import RANGE_REPLAY_RESULT_SCHEMA_VERSION
from market_health.calibration.single_date_replay import (
    SINGLE_DATE_REPLAY_SCHEMA_VERSION,
)


class AuthoritativeReplayDatasetRowTest(unittest.TestCase):
    def test_record_has_stable_shape(self) -> None:
        row = _row()

        self.assertEqual(
            tuple(row.to_record().keys()),
            AUTHORITATIVE_REPLAY_DATASET_COLUMNS,
        )
        self.assertEqual(
            row.to_record()["schema_version"],
            AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION,
        )
        self.assertEqual(row.to_record()["replay_date"], "2026-05-20")
        self.assertEqual(row.to_record()["symbol"], "SPY")
        self.assertEqual(row.to_record()["current_score"], 5.1)
        self.assertEqual(row.to_record()["h1_score"], 5.2)
        self.assertEqual(row.to_record()["h5_score"], 5.3)
        self.assertEqual(row.to_record()["blend_score"], 5.2)
        self.assertEqual(row.to_record()["state"], "YELLOW")
        self.assertEqual(row.to_record()["horizon"], "H1")
        self.assertIsNone(row.to_record()["target_date"])
        self.assertIsNone(row.to_record()["realized_current_score"])
        self.assertIsNone(row.to_record()["realized_return"])
        self.assertEqual(
            row.to_record()["realized_outcome_status"],
            REALIZED_OUTCOME_NOT_APPLICABLE,
        )
        self.assertEqual(row.to_record()["category"], "A")
        self.assertEqual(row.to_record()["slot"], 1)
        self.assertEqual(row.to_record()["category_slot"], "A1")
        self.assertEqual(row.to_record()["glyph"], "h1")
        self.assertEqual(row.to_record()["named_check"], "Trend Confirmation")
        self.assertEqual(row.to_record()["check_score"], 1.1)
        self.assertEqual(row.to_record()["replayability_class"], "replayable")
        self.assertEqual(row.to_record()["measurement_status"], MEASUREMENT_MEASURED)
        self.assertEqual(row.to_record()["source_module"], "fixture.module")
        self.assertEqual(row.to_record()["function_name"], "fixture_check")
        self.assertEqual(
            row.to_record()["replay_row_schema_version"],
            "calibration_replay_artifact_row.v1",
        )
        self.assertEqual(
            row.to_record()["check_row_schema_version"],
            CHECK_REPLAY_ROW_SCHEMA_VERSION,
        )
        self.assertEqual(
            row.to_record()["single_date_replay_schema_version"],
            SINGLE_DATE_REPLAY_SCHEMA_VERSION,
        )
        self.assertEqual(
            row.to_record()["range_replay_schema_version"],
            RANGE_REPLAY_RESULT_SCHEMA_VERSION,
        )
        self.assertEqual(
            row.to_record()["audit_token"],
            "single-date-asof:2026-05-20:SPY:2:101.0000",
        )
        self.assertEqual(
            row.to_record()["dataset_run_id"],
            "authoritative-replay-dataset",
        )

    def test_normalizes_symbol_category_horizon_and_state(self) -> None:
        row = _row(symbol=" spy ", category=" a ", horizon=" h5 ", state=" yellow ")

        self.assertEqual(row.symbol, "SPY")
        self.assertEqual(row.category, "A")
        self.assertEqual(row.horizon, "H5")
        self.assertEqual(row.state, "YELLOW")
        self.assertEqual(row.category_slot, "A1")

    def test_available_realized_outcome_requires_all_outcome_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires target_date"):
            _row(realized_outcome_status=REALIZED_OUTCOME_AVAILABLE)

        with self.assertRaisesRegex(ValueError, "requires realized_current_score"):
            _row(
                realized_outcome_status=REALIZED_OUTCOME_AVAILABLE,
                target_date=date(2026, 5, 21),
            )

        with self.assertRaisesRegex(ValueError, "requires realized_return"):
            _row(
                realized_outcome_status=REALIZED_OUTCOME_AVAILABLE,
                target_date=date(2026, 5, 21),
                realized_current_score=5.7,
            )

    def test_available_realized_outcome_serializes_target_fields(self) -> None:
        record = _row(
            realized_outcome_status=REALIZED_OUTCOME_AVAILABLE,
            target_date=date(2026, 5, 21),
            realized_current_score=5.7,
            realized_return=0.015,
        ).to_record()

        self.assertEqual(record["target_date"], "2026-05-21")
        self.assertEqual(record["realized_current_score"], 5.7)
        self.assertEqual(record["realized_return"], 0.015)
        self.assertEqual(record["realized_outcome_status"], REALIZED_OUTCOME_AVAILABLE)

    def test_missing_realized_outcome_can_record_target_date_without_values(
        self,
    ) -> None:
        record = _row(
            realized_outcome_status=REALIZED_OUTCOME_MISSING,
            target_date=date(2026, 5, 25),
        ).to_record()

        self.assertEqual(record["target_date"], "2026-05-25")
        self.assertIsNone(record["realized_current_score"])
        self.assertIsNone(record["realized_return"])
        self.assertEqual(record["realized_outcome_status"], REALIZED_OUTCOME_MISSING)

    def test_not_applicable_rejects_outcome_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot set target_date"):
            _row(target_date=date(2026, 5, 21))

        with self.assertRaisesRegex(ValueError, "cannot set realized_current_score"):
            _row(realized_current_score=5.0)

        with self.assertRaisesRegex(ValueError, "cannot set realized_return"):
            _row(realized_return=0.01)

    def test_rejects_invalid_schema_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported authoritative"):
            _row(schema_version="bad")


def _row(**overrides: object) -> AuthoritativeReplayDatasetRow:
    values = {
        "replay_date": date(2026, 5, 20),
        "symbol": "SPY",
        "current_score": 5.1,
        "h1_score": 5.2,
        "h5_score": 5.3,
        "blend_score": 5.2,
        "state": "YELLOW",
        "horizon": "H1",
        "category": "A",
        "slot": 1,
        "glyph": "h1",
        "named_check": "Trend Confirmation",
        "check_score": 1.1,
        "replayability_class": "replayable",
        "measurement_status": MEASUREMENT_MEASURED,
        "source_module": "fixture.module",
        "function_name": "fixture_check",
        "audit_token": "single-date-asof:2026-05-20:SPY:2:101.0000",
    }
    values.update(overrides)
    return AuthoritativeReplayDatasetRow(**values)


if __name__ == "__main__":
    unittest.main()
