from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.residual_attribution_export import (
    RESIDUAL_ATTRIBUTION_ROWS_TABLE,
    RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE,
    residual_attribution_rows_to_records,
    residual_attribution_summaries_to_records,
    sqlite_type_for_residual_attribution_column,
    write_residual_attribution_rows_csv,
    write_residual_attribution_sqlite,
    write_residual_attribution_summaries_csv,
)
from market_health.calibration.residuals import (
    RESIDUAL_ATTRIBUTION_COLUMNS,
    RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS,
    ResidualAttributionRow,
    ResidualAttributionSummaryRow,
)


class ResidualAttributionExportTest(unittest.TestCase):
    def test_rows_to_records_sorts_deterministically(self) -> None:
        records = residual_attribution_rows_to_records(
            [
                row(symbol="SPY", category="B", slot=4, horizon="H5"),
                row(symbol="QQQ", category="A", slot=1, horizon="H1"),
            ]
        )

        self.assertEqual([record["symbol"] for record in records], ["QQQ", "SPY"])

    def test_summaries_to_records_sorts_deterministically(self) -> None:
        records = residual_attribution_summaries_to_records(
            [
                summary(group_name="horizon+category", group_value="H1|B"),
                summary(group_name="horizon", group_value="H1"),
            ]
        )

        self.assertEqual(
            [(record["group_name"], record["group_value"]) for record in records],
            [("horizon", "H1"), ("horizon+category", "H1|B")],
        )

    def test_write_residual_attribution_rows_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.csv"

            write_residual_attribution_rows_csv(path, [row()])

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(tuple(rows[0].keys()), RESIDUAL_ATTRIBUTION_COLUMNS)
        self.assertEqual(rows[0]["symbol"], "SPY")
        self.assertEqual(rows[0]["residual"], "0.5")

    def test_write_residual_attribution_summaries_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "summaries.csv"

            write_residual_attribution_summaries_csv(path, [summary()])

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(tuple(rows[0].keys()), RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS)
        self.assertEqual(rows[0]["group_name"], "horizon")
        self.assertEqual(rows[0]["observation_count"], "2")

    def test_write_residual_attribution_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "residuals.sqlite"

            write_residual_attribution_sqlite(
                path,
                rows=[
                    row(),
                    row(
                        symbol="QQQ",
                        forecast_score=7.25,
                        realized_current_score=7.5,
                        residual=-0.25,
                        residual_direction="cold",
                    ),
                ],
                summaries=[summary()],
            )

            with sqlite3.connect(path) as connection:
                row_count = connection.execute(
                    f"SELECT COUNT(*) FROM {RESIDUAL_ATTRIBUTION_ROWS_TABLE}"
                ).fetchone()[0]
                summary_count = connection.execute(
                    f"SELECT COUNT(*) FROM {RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE}"
                ).fetchone()[0]
                residual_sum = connection.execute(
                    f"SELECT ROUND(SUM(residual), 2) FROM {RESIDUAL_ATTRIBUTION_ROWS_TABLE}"
                ).fetchone()[0]

        self.assertEqual(row_count, 2)
        self.assertEqual(summary_count, 1)
        self.assertEqual(residual_sum, 0.25)

    def test_sqlite_type_mapping(self) -> None:
        self.assertEqual(
            sqlite_type_for_residual_attribution_column("residual"), "REAL"
        )
        self.assertEqual(
            sqlite_type_for_residual_attribution_column("observation_count"),
            "INTEGER",
        )
        self.assertEqual(sqlite_type_for_residual_attribution_column("symbol"), "TEXT")


def row(
    *,
    symbol: str = "SPY",
    horizon: str = "H1",
    category: str = "B",
    slot: int = 4,
    forecast_score: float = 8.5,
    realized_current_score: float = 8.0,
    residual: float = 0.5,
    residual_direction: str = "hot",
) -> ResidualAttributionRow:
    return ResidualAttributionRow(
        replay_date=date(2026, 5, 20),
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


def summary(
    *,
    group_name: str = "horizon",
    group_value: str = "H1",
) -> ResidualAttributionSummaryRow:
    return ResidualAttributionSummaryRow(
        group_name=group_name,
        group_value=group_value,
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
