from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.calibration_review import (
    CALIBRATION_REVIEW_WINDOW_SUMMARY_COLUMNS,
    CALIBRATION_REVIEW_WINDOW_SUMMARY_SCHEMA_VERSION,
    CalibrationReviewWindow,
    build_trailing_calibration_review_windows,
    build_windowed_calibration_review_tables,
    residual_rows_for_calibration_review_window,
)
from market_health.calibration.residuals import ResidualAttributionRow


class CalibrationReviewWindowTest(unittest.TestCase):
    def test_trailing_windows_use_latest_replay_date_by_default(self) -> None:
        windows = build_trailing_calibration_review_windows(
            (
                residual_row(replay_date=date(2026, 5, 1)),
                residual_row(symbol="QQQ", replay_date=date(2026, 5, 20)),
            ),
            day_counts=(7, 30),
        )

        self.assertEqual(
            [(window.label, window.start_date, window.end_date) for window in windows],
            [
                ("full", None, None),
                ("7d", date(2026, 5, 14), date(2026, 5, 20)),
                ("30d", date(2026, 4, 21), date(2026, 5, 20)),
            ],
        )

    def test_trailing_windows_can_use_explicit_as_of_date(self) -> None:
        windows = build_trailing_calibration_review_windows(
            (),
            include_full_window=False,
            day_counts=(3,),
            as_of_date=date(2026, 6, 10),
        )

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].label, "3d")
        self.assertEqual(windows[0].start_date, date(2026, 6, 8))
        self.assertEqual(windows[0].end_date, date(2026, 6, 10))

    def test_filters_rows_inclusive_by_window_bounds(self) -> None:
        window = CalibrationReviewWindow(
            "two-day",
            start_date=date(2026, 5, 19),
            end_date=date(2026, 5, 20),
        )

        rows = residual_rows_for_calibration_review_window(
            (
                residual_row(symbol="OLD", replay_date=date(2026, 5, 18)),
                residual_row(symbol="SPY", replay_date=date(2026, 5, 19)),
                residual_row(symbol="QQQ", replay_date=date(2026, 5, 20)),
                residual_row(symbol="NEW", replay_date=date(2026, 5, 21)),
            ),
            window,
        )

        self.assertEqual([row.symbol for row in rows], ["SPY", "QQQ"])

    def test_rejects_bad_window_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "window_start_date"):
            CalibrationReviewWindow(
                "bad",
                start_date=date(2026, 5, 21),
                end_date=date(2026, 5, 20),
            )

        with self.assertRaisesRegex(ValueError, "positive"):
            build_trailing_calibration_review_windows((), day_counts=(0,))

        with self.assertRaisesRegex(ValueError, "unique"):
            build_trailing_calibration_review_windows((), day_counts=(7, 7))


class CalibrationReviewWindowedTablesTest(unittest.TestCase):
    def test_builds_full_and_windowed_review_tables(self) -> None:
        rows = (
            residual_row(symbol="OLD", replay_date=date(2026, 4, 1)),
            residual_row(
                symbol="SPY",
                replay_date=date(2026, 5, 19),
                residual=0.5,
                residual_direction="hot",
            ),
            residual_row(
                symbol="QQQ",
                replay_date=date(2026, 5, 20),
                forecast_score=8.25,
                realized_current_score=8.0,
                residual=0.25,
                residual_direction="hot",
            ),
            residual_row(
                symbol="IWM",
                replay_date=date(2026, 5, 20),
                named_check="breadth_confirmed",
                category="C",
                slot=2,
                glyph="-",
                forecast_score=7.25,
                realized_current_score=8.0,
                residual=-0.75,
                residual_direction="cold",
            ),
        )
        windows = (
            CalibrationReviewWindow("full"),
            CalibrationReviewWindow(
                "2d",
                start_date=date(2026, 5, 19),
                end_date=date(2026, 5, 20),
            ),
        )

        tables = build_windowed_calibration_review_tables(
            rows,
            windows=windows,
            min_observation_count=2,
            max_examples_per_group=1,
        )

        self.assertEqual([table.window.label for table in tables], ["full", "2d"])
        full = tables[0]
        two_day = tables[1]

        self.assertEqual(full.residual_observation_count, 4)
        self.assertEqual(len(full.glyph_review_rows), 2)
        self.assertEqual(len(full.named_check_review_rows), 2)
        self.assertEqual(len(full.glyph_example_rows), 2)
        self.assertEqual(len(full.named_check_example_rows), 2)

        self.assertEqual(two_day.residual_observation_count, 3)
        self.assertEqual(len(two_day.glyph_review_rows), 2)
        self.assertEqual(len(two_day.named_check_review_rows), 2)
        self.assertEqual(len(two_day.glyph_example_rows), 2)
        self.assertEqual(len(two_day.named_check_example_rows), 2)

        self.assertEqual(two_day.glyph_review_rows[0].window_label, "2d")
        self.assertEqual(
            two_day.glyph_review_rows[0].window_start_date, date(2026, 5, 19)
        )
        self.assertEqual(
            two_day.glyph_review_rows[0].window_end_date, date(2026, 5, 20)
        )
        self.assertEqual(two_day.glyph_example_rows[0].window_label, "2d")

    def test_summary_record_has_stable_shape(self) -> None:
        tables = build_windowed_calibration_review_tables(
            (residual_row(),),
            windows=(CalibrationReviewWindow("full"),),
        )

        record = tables[0].to_summary_record()

        self.assertEqual(
            tuple(record.keys()), CALIBRATION_REVIEW_WINDOW_SUMMARY_COLUMNS
        )
        self.assertEqual(
            record["schema_version"],
            CALIBRATION_REVIEW_WINDOW_SUMMARY_SCHEMA_VERSION,
        )
        self.assertEqual(record["window_label"], "full")
        self.assertIsNone(record["window_start_date"])
        self.assertIsNone(record["window_end_date"])
        self.assertEqual(record["residual_observation_count"], 1)
        self.assertEqual(record["glyph_review_row_count"], 1)
        self.assertEqual(record["named_check_review_row_count"], 1)
        self.assertEqual(record["glyph_example_row_count"], 1)
        self.assertEqual(record["named_check_example_row_count"], 1)
        self.assertEqual(record["residual_attribution_run_id"], "m53-test")

    def test_empty_window_emits_empty_tables_and_summary(self) -> None:
        tables = build_windowed_calibration_review_tables(
            (residual_row(replay_date=date(2026, 5, 1)),),
            windows=(
                CalibrationReviewWindow(
                    "empty",
                    start_date=date(2026, 5, 20),
                    end_date=date(2026, 5, 21),
                ),
            ),
        )

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].residual_observation_count, 0)
        self.assertEqual(tables[0].glyph_review_rows, ())
        self.assertEqual(tables[0].named_check_review_rows, ())
        self.assertEqual(tables[0].glyph_example_rows, ())
        self.assertEqual(tables[0].named_check_example_rows, ())
        self.assertIsNone(tables[0].residual_attribution_run_id)

    def test_rejects_empty_and_duplicate_window_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            build_windowed_calibration_review_tables((residual_row(),), windows=())

        with self.assertRaisesRegex(ValueError, "unique"):
            build_windowed_calibration_review_tables(
                (residual_row(),),
                windows=(CalibrationReviewWindow("x"), CalibrationReviewWindow("x")),
            )

    def test_rejects_mixed_run_ids_inside_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "residual_attribution_run_id"):
            build_windowed_calibration_review_tables(
                (
                    residual_row(residual_attribution_run_id="run-a"),
                    residual_row(symbol="QQQ", residual_attribution_run_id="run-b"),
                )
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
