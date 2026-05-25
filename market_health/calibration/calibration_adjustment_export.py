from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from market_health.calibration.calibration_adjustments import (
    CALIBRATION_ADJUSTMENT_CANDIDATE_COLUMNS,
    CALIBRATION_DRY_RUN_COMPARISON_COLUMNS,
    CALIBRATION_DRY_RUN_COMPARISON_GROUPS,
    CALIBRATION_DRY_RUN_SIMULATION_COLUMNS,
    CalibrationAdjustmentCandidateRow,
    CalibrationDryRunComparisonRow,
    CalibrationDryRunSimulationRow,
)
from market_health.calibration.defaults import assert_not_live_runtime_path

CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE = "calibration_adjustment_candidates"
CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE = "calibration_dry_run_simulation_rows"
CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE = "calibration_dry_run_comparison_rows"


def calibration_adjustment_candidates_to_records(
    rows: Iterable[CalibrationAdjustmentCandidateRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_candidate_row_sort_key))


def calibration_dry_run_simulation_rows_to_records(
    rows: Iterable[CalibrationDryRunSimulationRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_simulation_row_sort_key))


def calibration_dry_run_comparison_rows_to_records(
    rows: Iterable[CalibrationDryRunComparisonRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_comparison_row_sort_key))


def write_calibration_adjustment_candidates_csv(
    path: Path,
    rows: Iterable[CalibrationAdjustmentCandidateRow],
) -> None:
    _write_csv(
        path,
        calibration_adjustment_candidates_to_records(rows),
        CALIBRATION_ADJUSTMENT_CANDIDATE_COLUMNS,
    )


def write_calibration_dry_run_simulation_rows_csv(
    path: Path,
    rows: Iterable[CalibrationDryRunSimulationRow],
) -> None:
    _write_csv(
        path,
        calibration_dry_run_simulation_rows_to_records(rows),
        CALIBRATION_DRY_RUN_SIMULATION_COLUMNS,
    )


def write_calibration_dry_run_comparison_rows_csv(
    path: Path,
    rows: Iterable[CalibrationDryRunComparisonRow],
) -> None:
    _write_csv(
        path,
        calibration_dry_run_comparison_rows_to_records(rows),
        CALIBRATION_DRY_RUN_COMPARISON_COLUMNS,
    )


def write_calibration_dry_run_sqlite(
    path: Path,
    *,
    candidates: Iterable[CalibrationAdjustmentCandidateRow],
    simulation_rows: Iterable[CalibrationDryRunSimulationRow],
    comparison_rows: Iterable[CalibrationDryRunComparisonRow],
    candidates_table_name: str = CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE,
    simulation_rows_table_name: str = CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE,
    comparison_rows_table_name: str = CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE,
) -> None:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    candidate_records = calibration_adjustment_candidates_to_records(candidates)
    simulation_records = calibration_dry_run_simulation_rows_to_records(simulation_rows)
    comparison_records = calibration_dry_run_comparison_rows_to_records(comparison_rows)

    with sqlite3.connect(path) as connection:
        _write_table(
            connection,
            table_name=candidates_table_name,
            columns=CALIBRATION_ADJUSTMENT_CANDIDATE_COLUMNS,
            records=candidate_records,
        )
        _write_table(
            connection,
            table_name=simulation_rows_table_name,
            columns=CALIBRATION_DRY_RUN_SIMULATION_COLUMNS,
            records=simulation_records,
        )
        _write_table(
            connection,
            table_name=comparison_rows_table_name,
            columns=CALIBRATION_DRY_RUN_COMPARISON_COLUMNS,
            records=comparison_records,
        )


def sqlite_type_for_calibration_dry_run_column(column: str) -> str:
    if column in {
        "score_delta",
        "mean_residual",
        "mean_abs_residual",
        "baseline_forecast_score",
        "simulated_forecast_score",
        "realized_current_score",
        "baseline_residual",
        "simulated_residual",
        "applied_score_delta",
        "baseline_mean_residual",
        "simulated_mean_residual",
        "baseline_mean_abs_residual",
        "simulated_mean_abs_residual",
        "mean_abs_residual_delta",
        "mean_abs_residual_improvement",
    }:
        return "REAL"
    if column in {
        "slot",
        "observation_count",
        "applied_candidate_count",
        "improved_count",
        "worsened_count",
        "unchanged_count",
        "baseline_hot_count",
        "baseline_cold_count",
        "baseline_neutral_count",
        "simulated_hot_count",
        "simulated_cold_count",
        "simulated_neutral_count",
        "unique_applied_candidate_count",
    }:
        return "INTEGER"
    return "TEXT"


def _write_csv(
    path: Path,
    records: tuple[dict[str, object], ...],
    columns: tuple[str, ...],
) -> None:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def _write_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    columns: tuple[str, ...],
    records: tuple[dict[str, object], ...],
) -> None:
    quoted_table = _quote_identifier(table_name)
    connection.execute(f"DROP TABLE IF EXISTS {quoted_table}")
    column_sql = ", ".join(
        f"{_quote_identifier(column)} {sqlite_type_for_calibration_dry_run_column(column)}"
        for column in columns
    )
    connection.execute(f"CREATE TABLE {quoted_table} ({column_sql})")

    if not records:
        return

    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    connection.executemany(
        f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})",
        [[record[column] for column in columns] for record in records],
    )


def _quote_identifier(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def _optional_date_sort_key(value: object) -> str:
    return "" if value is None else str(value)


def _candidate_row_sort_key(
    row: CalibrationAdjustmentCandidateRow,
) -> tuple[object, ...]:
    return (row.candidate_id,)


def _simulation_row_sort_key(
    row: CalibrationDryRunSimulationRow,
) -> tuple[object, ...]:
    return (
        row.replay_date.isoformat(),
        row.symbol,
        row.horizon,
        row.category,
        row.slot,
        row.glyph,
        row.named_check,
    )


def _comparison_row_sort_key(
    row: CalibrationDryRunComparisonRow,
) -> tuple[object, ...]:
    return (
        CALIBRATION_DRY_RUN_COMPARISON_GROUPS.index(row.group_name),
        row.group_value,
    )
