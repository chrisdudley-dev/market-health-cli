from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.check_output import (
    CHECK_REPLAY_ROW_COLUMNS,
    CHECK_REPLAY_ROW_SCHEMA_VERSION,
    MEASUREMENT_EVENT_UNAVAILABLE,
    MEASUREMENT_FALLBACK_NEUTRAL,
    MEASUREMENT_MEASURED,
    CheckReplayRow,
    build_fixture_check_replay_rows,
)


class CheckReplayOutputTest(unittest.TestCase):
    def test_check_replay_row_record_shape(self) -> None:
        row = CheckReplayRow(
            replay_date=date(2026, 5, 22),
            symbol="spy",
            category="b",
            slot=5,
            horizon="h1",
            glyph="h5",
            named_check="Participation Trend",
            score=5.1,
            replayability_class="replayable",
            measurement_status="measured",
            source_module="market_health.forecast_checks_b_backdrop",
            function_name="b5_participation_trend",
        )

        record = row.to_record()

        self.assertEqual(tuple(record), CHECK_REPLAY_ROW_COLUMNS)
        self.assertEqual(record["schema_version"], CHECK_REPLAY_ROW_SCHEMA_VERSION)
        self.assertEqual(record["replay_date"], "2026-05-22")
        self.assertEqual(record["symbol"], "SPY")
        self.assertEqual(record["category_slot"], "B5")
        self.assertEqual(record["horizon"], "H1")

    def test_fixture_rows_cover_symbols_inventory_and_horizons(self) -> None:
        rows = build_fixture_check_replay_rows(
            replay_date=date(2026, 5, 22),
            symbols=["SPY", "QQQ"],
        )

        self.assertEqual(len(rows), 180)
        self.assertEqual(rows[0].symbol, "QQQ")
        self.assertEqual(rows[0].category_slot, "A1")
        self.assertEqual(rows[0].horizon, "C")
        self.assertEqual(rows[-1].symbol, "SPY")
        self.assertEqual(rows[-1].category_slot, "E6")
        self.assertEqual(rows[-1].horizon, "H5")

    def test_fixture_rows_preserve_replayability_measurement_statuses(self) -> None:
        rows = build_fixture_check_replay_rows(
            replay_date=date(2026, 5, 22),
            symbols=["SPY"],
            horizons=["C"],
        )
        by_slot = {row.category_slot: row for row in rows}

        self.assertEqual(
            by_slot["A1"].measurement_status, MEASUREMENT_EVENT_UNAVAILABLE
        )
        self.assertEqual(by_slot["B5"].measurement_status, MEASUREMENT_MEASURED)
        self.assertEqual(by_slot["E5"].measurement_status, MEASUREMENT_FALLBACK_NEUTRAL)

    def test_invalid_horizon_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported check horizon"):
            build_fixture_check_replay_rows(
                replay_date=date(2026, 5, 22),
                symbols=["SPY"],
                horizons=["H2"],
            )


if __name__ == "__main__":
    unittest.main()
