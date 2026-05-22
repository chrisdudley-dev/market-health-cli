from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from market_health.calibration.check_inventory import (
    CHECK_INVENTORY_COLUMNS,
    REPLAYABILITY_CLASSES,
    REPLAYABILITY_EVENT_DEPENDENT,
    REPLAYABILITY_EXCLUDED,
    REPLAYABILITY_NEUTRAL_FALLBACK,
    REPLAYABILITY_REPLAYABLE,
    check_inventory_records,
    iter_check_inventory,
    write_check_inventory_csv,
    write_check_inventory_json,
)


class CheckInventoryTest(unittest.TestCase):
    def test_inventory_has_six_ordered_checks_per_category(self) -> None:
        rows = iter_check_inventory()

        self.assertEqual(len(rows), 30)
        self.assertEqual(
            [(row.category, row.slot) for row in rows[:6]],
            [("A", 1), ("A", 2), ("A", 3), ("A", 4), ("A", 5), ("A", 6)],
        )
        self.assertEqual(
            [(row.category, row.slot) for row in rows[-6:]],
            [("E", 1), ("E", 2), ("E", 3), ("E", 4), ("E", 5), ("E", 6)],
        )

    def test_inventory_supports_all_replayability_classes(self) -> None:
        self.assertEqual(
            REPLAYABILITY_CLASSES,
            (
                REPLAYABILITY_REPLAYABLE,
                REPLAYABILITY_EVENT_DEPENDENT,
                REPLAYABILITY_NEUTRAL_FALLBACK,
                REPLAYABILITY_EXCLUDED,
            ),
        )

        classes_in_inventory = {
            row.replayability_class for row in iter_check_inventory()
        }

        self.assertIn(REPLAYABILITY_REPLAYABLE, classes_in_inventory)
        self.assertIn(REPLAYABILITY_EVENT_DEPENDENT, classes_in_inventory)
        self.assertIn(REPLAYABILITY_NEUTRAL_FALLBACK, classes_in_inventory)

    def test_inventory_records_have_stable_shape(self) -> None:
        records = check_inventory_records()
        first = records[0]

        self.assertEqual(tuple(first), CHECK_INVENTORY_COLUMNS)
        self.assertEqual(first["category_slot"], "A1")
        self.assertEqual(first["named_check"], "Catalyst Window")
        self.assertEqual(first["replayability_class"], "event_dependent")

    def test_cross_regime_pressure_records_fallback_policy(self) -> None:
        rows = {row.category_slot: row for row in iter_check_inventory()}

        e5 = rows["E5"]

        self.assertEqual(e5.named_check, "Cross-Regime Pressure")
        self.assertEqual(e5.replayability_class, REPLAYABILITY_NEUTRAL_FALLBACK)
        self.assertIn("measured neutral", e5.fallback_policy)

    def test_writers_emit_deterministic_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = write_check_inventory_json(root / "inventory.json")
            csv_path = write_check_inventory_csv(root / "inventory.csv")

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open(newline="", encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))

        self.assertEqual(
            payload["schema_version"],
            "calibration_check_inventory.v1",
        )
        self.assertEqual(len(payload["rows"]), 30)
        self.assertEqual(len(csv_rows), 30)
        self.assertEqual(csv_rows[0]["category_slot"], "A1")
        self.assertEqual(csv_rows[-1]["category_slot"], "E6")


if __name__ == "__main__":
    unittest.main()
