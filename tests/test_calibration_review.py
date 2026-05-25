from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_review import (
    CALIBRATION_GLYPH_REVIEW_COLUMNS,
    CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION,
    CALIBRATION_NAMED_CHECK_REVIEW_COLUMNS,
    CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION,
    REVIEW_COLD,
    REVIEW_HOT,
    REVIEW_INCONCLUSIVE,
    CalibrationGlyphReviewRow,
    CalibrationNamedCheckReviewRow,
)


class CalibrationGlyphReviewRowTest(unittest.TestCase):
    def test_record_has_stable_shape(self) -> None:
        row = glyph_review_row()

        record = row.to_record()

        self.assertEqual(tuple(record.keys()), CALIBRATION_GLYPH_REVIEW_COLUMNS)
        self.assertEqual(
            record["schema_version"],
            CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION,
        )
        self.assertEqual(record["window_label"], "full")
        self.assertIsNone(record["window_start_date"])
        self.assertIsNone(record["window_end_date"])
        self.assertEqual(record["horizon"], "H1")
        self.assertEqual(record["category"], "B")
        self.assertEqual(record["slot"], 4)
        self.assertEqual(record["category_slot"], "B4")
        self.assertEqual(record["glyph"], "+")
        self.assertEqual(record["observation_count"], 5)
        self.assertEqual(record["min_observation_count"], 3)
        self.assertEqual(record["mean_residual"], 0.32)
        self.assertEqual(record["median_residual"], 0.25)
        self.assertEqual(record["mean_abs_residual"], 0.44)
        self.assertEqual(record["hot_count"], 4)
        self.assertEqual(record["cold_count"], 1)
        self.assertEqual(record["neutral_count"], 0)
        self.assertEqual(record["review_classification"], REVIEW_HOT)
        self.assertEqual(record["residual_attribution_run_id"], "m53-test")

    def test_normalizes_horizon_and_category(self) -> None:
        row = glyph_review_row(horizon=" h5 ", category=" b ")

        self.assertEqual(row.horizon, "H5")
        self.assertEqual(row.category, "B")
        self.assertEqual(row.category_slot, "B4")

    def test_rejects_direction_count_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "direction counts"):
            glyph_review_row(
                observation_count=5, hot_count=3, cold_count=1, neutral_count=0
            )

    def test_low_sample_rows_must_be_inconclusive(self) -> None:
        with self.assertRaisesRegex(ValueError, "inconclusive"):
            glyph_review_row(
                observation_count=2,
                min_observation_count=3,
                hot_count=2,
                cold_count=0,
                neutral_count=0,
                review_classification=REVIEW_HOT,
            )

        row = glyph_review_row(
            observation_count=2,
            min_observation_count=3,
            hot_count=2,
            cold_count=0,
            neutral_count=0,
            review_classification=REVIEW_INCONCLUSIVE,
        )
        self.assertEqual(row.review_classification, REVIEW_INCONCLUSIVE)

    def test_rejects_bad_window_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "window_start_date"):
            glyph_review_row(
                window_start_date=date(2026, 5, 22),
                window_end_date=date(2026, 5, 20),
            )


class CalibrationNamedCheckReviewRowTest(unittest.TestCase):
    def test_record_has_stable_shape(self) -> None:
        row = named_check_review_row()

        record = row.to_record()

        self.assertEqual(tuple(record.keys()), CALIBRATION_NAMED_CHECK_REVIEW_COLUMNS)
        self.assertEqual(
            record["schema_version"],
            CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION,
        )
        self.assertEqual(record["window_label"], "full")
        self.assertEqual(record["horizon"], "H1")
        self.assertEqual(record["named_check"], "trend_confirmed")
        self.assertEqual(record["category"], "B")
        self.assertEqual(record["slot"], 4)
        self.assertEqual(record["category_slot"], "B4")
        self.assertEqual(record["glyph"], "+")
        self.assertEqual(record["review_classification"], REVIEW_COLD)

    def test_infers_category_slot_when_category_and_slot_are_available(self) -> None:
        row = named_check_review_row(category_slot=None)

        self.assertEqual(row.category_slot, "B4")

    def test_rejects_category_slot_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "category_slot"):
            named_check_review_row(category_slot="B5")

    def test_allows_named_check_without_category_context(self) -> None:
        row = named_check_review_row(
            category=None, slot=None, category_slot=None, glyph=None
        )

        self.assertIsNone(row.category)
        self.assertIsNone(row.slot)
        self.assertIsNone(row.category_slot)
        self.assertIsNone(row.glyph)

    def test_rejects_invalid_schema_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema version"):
            named_check_review_row(schema_version="bad")


def glyph_review_row(
    *,
    horizon: str = "H1",
    category: str = "B",
    slot: int = 4,
    glyph: str = "+",
    observation_count: int = 5,
    min_observation_count: int = 3,
    mean_residual: float = 0.32,
    median_residual: float = 0.25,
    mean_abs_residual: float = 0.44,
    hot_count: int = 4,
    cold_count: int = 1,
    neutral_count: int = 0,
    review_classification: str = REVIEW_HOT,
    residual_attribution_run_id: str = "m53-test",
    window_label: str = "full",
    window_start_date: date | None = None,
    window_end_date: date | None = None,
    schema_version: str = CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION,
) -> CalibrationGlyphReviewRow:
    return CalibrationGlyphReviewRow(
        horizon=horizon,
        category=category,
        slot=slot,
        glyph=glyph,
        observation_count=observation_count,
        min_observation_count=min_observation_count,
        mean_residual=mean_residual,
        median_residual=median_residual,
        mean_abs_residual=mean_abs_residual,
        hot_count=hot_count,
        cold_count=cold_count,
        neutral_count=neutral_count,
        review_classification=review_classification,
        residual_attribution_run_id=residual_attribution_run_id,
        window_label=window_label,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
        schema_version=schema_version,
    )


def named_check_review_row(
    *,
    horizon: str = "H1",
    named_check: str = "trend_confirmed",
    category: str | None = "B",
    slot: int | None = 4,
    category_slot: str | None = "B4",
    glyph: str | None = "+",
    observation_count: int = 4,
    min_observation_count: int = 3,
    mean_residual: float = -0.3,
    median_residual: float = -0.25,
    mean_abs_residual: float = 0.4,
    hot_count: int = 1,
    cold_count: int = 3,
    neutral_count: int = 0,
    review_classification: str = REVIEW_COLD,
    residual_attribution_run_id: str = "m53-test",
    window_label: str = "full",
    window_start_date: date | None = None,
    window_end_date: date | None = None,
    schema_version: str = CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION,
) -> CalibrationNamedCheckReviewRow:
    return CalibrationNamedCheckReviewRow(
        horizon=horizon,
        named_check=named_check,
        category=category,
        slot=slot,
        category_slot=category_slot,
        glyph=glyph,
        observation_count=observation_count,
        min_observation_count=min_observation_count,
        mean_residual=mean_residual,
        median_residual=median_residual,
        mean_abs_residual=mean_abs_residual,
        hot_count=hot_count,
        cold_count=cold_count,
        neutral_count=neutral_count,
        review_classification=review_classification,
        residual_attribution_run_id=residual_attribution_run_id,
        window_label=window_label,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
        schema_version=schema_version,
    )


if __name__ == "__main__":
    unittest.main()
