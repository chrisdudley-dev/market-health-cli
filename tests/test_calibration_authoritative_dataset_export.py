from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.authoritative_dataset import (
    AUTHORITATIVE_REPLAY_DATASET_COLUMNS,
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_NOT_APPLICABLE,
    AuthoritativeReplayDatasetRow,
)
from market_health.calibration.authoritative_dataset_export import (
    AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE,
    authoritative_dataset_rows_to_records,
    sqlite_type_for_authoritative_dataset_column,
    write_authoritative_dataset_rows_csv,
    write_authoritative_dataset_rows_sqlite,
)
from market_health.calibration.check_output import MEASUREMENT_MEASURED


class AuthoritativeDatasetExportTest(unittest.TestCase):
    def test_rows_to_records_sorts_deterministically(self) -> None:
        records = authoritative_dataset_rows_to_records(
            [
                _row(category="B", slot=2, horizon="H5"),
                _row(category="A", slot=1, horizon="C"),
                _row(category="A", slot=2, horizon="H1"),
            ]
        )

        self.assertEqual(
            [(item["category"], item["slot"], item["horizon"]) for item in records],
            [("A", 1, "C"), ("A", 2, "H1"), ("B", 2, "H5")],
        )
        self.assertEqual(tuple(records[0].keys()), AUTHORITATIVE_REPLAY_DATASET_COLUMNS)

    def test_write_authoritative_dataset_rows_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_authoritative_dataset_rows_csv(
                Path(tmp) / "authoritative_dataset.csv",
                [_row(horizon="H1", target_date=date(2026, 5, 21))],
            )

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(
            rows[0]["schema_version"], "calibration_authoritative_replay_dataset.v1"
        )
        self.assertEqual(rows[0]["replay_date"], "2026-05-20")
        self.assertEqual(rows[0]["symbol"], "SPY")
        self.assertEqual(rows[0]["horizon"], "H1")
        self.assertEqual(rows[0]["target_date"], "2026-05-21")
        self.assertEqual(rows[0]["realized_outcome_status"], REALIZED_OUTCOME_AVAILABLE)

    def test_write_authoritative_dataset_rows_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_authoritative_dataset_rows_sqlite(
                Path(tmp) / "authoritative_dataset.sqlite",
                [_row(horizon="H1", target_date=date(2026, 5, 21))],
            )

            with sqlite3.connect(path) as conn:
                fetched = conn.execute(
                    f"""
                    SELECT symbol, horizon, target_date, realized_return
                    FROM {AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE}
                    """
                ).fetchall()

        self.assertEqual(fetched, [("SPY", "H1", "2026-05-21", 0.03)])

    def test_sqlite_type_mapping(self) -> None:
        self.assertEqual(
            sqlite_type_for_authoritative_dataset_column("slot"), "INTEGER"
        )
        self.assertEqual(
            sqlite_type_for_authoritative_dataset_column("realized_return"),
            "REAL",
        )
        self.assertEqual(sqlite_type_for_authoritative_dataset_column("symbol"), "TEXT")


def _row(
    *,
    category: str = "A",
    slot: int = 1,
    horizon: str = "C",
    target_date: date | None = None,
) -> AuthoritativeReplayDatasetRow:
    is_current = horizon == "C"
    resolved_target_date = target_date or date(2026, 5, 21)
    return AuthoritativeReplayDatasetRow(
        replay_date=date(2026, 5, 20),
        symbol="SPY",
        current_score=5.1,
        h1_score=5.2,
        h5_score=5.3,
        blend_score=5.2,
        state="YELLOW",
        horizon=horizon,
        target_date=None if is_current else resolved_target_date,
        realized_current_score=None if is_current else 8.0,
        realized_return=None if is_current else 0.03,
        realized_outcome_status=(
            REALIZED_OUTCOME_NOT_APPLICABLE
            if is_current
            else REALIZED_OUTCOME_AVAILABLE
        ),
        category=category,
        slot=slot,
        glyph=f"{horizon.lower()[0]}{slot}",
        named_check=f"Check {category}{slot}",
        check_score=float(slot),
        replayability_class="replayable",
        measurement_status=MEASUREMENT_MEASURED,
        source_module="fixture.module",
        function_name=f"check_{category.lower()}{slot}",
        audit_token="single-date-asof:2026-05-20:SPY:1:100.0000",
        dataset_run_id="dataset-test",
    )


if __name__ == "__main__":
    unittest.main()
