from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.residuals import (
    RESIDUAL_ATTRIBUTION_COLUMNS,
    RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS,
    ResidualAttributionRow,
    ResidualAttributionSummaryRow,
)

RESIDUAL_ATTRIBUTION_ROWS_TABLE = "calibration_residual_attribution_rows"
RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE = "calibration_residual_attribution_summaries"


def residual_attribution_rows_to_records(
    rows: Iterable[ResidualAttributionRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_row_sort_key))


def residual_attribution_summaries_to_records(
    rows: Iterable[ResidualAttributionSummaryRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_summary_sort_key))


def write_residual_attribution_rows_csv(
    path: Path,
    rows: Iterable[ResidualAttributionRow],
) -> None:
    records = residual_attribution_rows_to_records(rows)
    _write_csv(path, records, RESIDUAL_ATTRIBUTION_COLUMNS)


def write_residual_attribution_summaries_csv(
    path: Path,
    rows: Iterable[ResidualAttributionSummaryRow],
) -> None:
    records = residual_attribution_summaries_to_records(rows)
    _write_csv(path, records, RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS)


def write_residual_attribution_sqlite(
    path: Path,
    *,
    rows: Iterable[ResidualAttributionRow],
    summaries: Iterable[ResidualAttributionSummaryRow],
    rows_table_name: str = RESIDUAL_ATTRIBUTION_ROWS_TABLE,
    summaries_table_name: str = RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE,
) -> None:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    row_records = residual_attribution_rows_to_records(rows)
    summary_records = residual_attribution_summaries_to_records(summaries)

    with sqlite3.connect(path) as connection:
        _write_table(
            connection,
            table_name=rows_table_name,
            columns=RESIDUAL_ATTRIBUTION_COLUMNS,
            records=row_records,
        )
        _write_table(
            connection,
            table_name=summaries_table_name,
            columns=RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS,
            records=summary_records,
        )


def sqlite_type_for_residual_attribution_column(column: str) -> str:
    if column in {
        "forecast_score",
        "realized_current_score",
        "residual",
        "realized_return",
        "mean_residual",
        "mean_abs_residual",
    }:
        return "REAL"
    if column in {
        "slot",
        "observation_count",
        "hot_count",
        "cold_count",
        "neutral_count",
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
        f"{_quote_identifier(column)} {sqlite_type_for_residual_attribution_column(column)}"
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


def _row_sort_key(row: ResidualAttributionRow) -> tuple[str, str, str, int, str, str]:
    return (
        row.replay_date.isoformat(),
        row.symbol,
        row.category,
        row.slot,
        row.horizon,
        row.named_check,
    )


def _summary_sort_key(
    row: ResidualAttributionSummaryRow,
) -> tuple[str, str, str | None, str | None, str | None]:
    return (
        row.group_name,
        row.group_value,
        row.horizon,
        row.category_slot,
        row.named_check,
    )
