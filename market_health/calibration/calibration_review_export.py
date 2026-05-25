from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from market_health.calibration.calibration_review import (
    CALIBRATION_GLYPH_REVIEW_COLUMNS,
    CALIBRATION_NAMED_CHECK_REVIEW_COLUMNS,
    CALIBRATION_REVIEW_EXAMPLE_COLUMNS,
    CALIBRATION_REVIEW_WINDOW_SUMMARY_COLUMNS,
    CalibrationGlyphReviewRow,
    CalibrationNamedCheckReviewRow,
    CalibrationReviewExampleRow,
    CalibrationReviewWindowedTables,
)
from market_health.calibration.defaults import assert_not_live_runtime_path

CALIBRATION_GLYPH_REVIEW_ROWS_TABLE = "calibration_glyph_review_rows"
CALIBRATION_NAMED_CHECK_REVIEW_ROWS_TABLE = "calibration_named_check_review_rows"
CALIBRATION_GLYPH_REVIEW_EXAMPLES_TABLE = "calibration_glyph_review_examples"
CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_TABLE = (
    "calibration_named_check_review_examples"
)
CALIBRATION_REVIEW_WINDOW_SUMMARIES_TABLE = "calibration_review_window_summaries"


def glyph_review_rows_to_records(
    rows: Iterable[CalibrationGlyphReviewRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_glyph_row_sort_key))


def named_check_review_rows_to_records(
    rows: Iterable[CalibrationNamedCheckReviewRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_named_check_row_sort_key))


def calibration_review_examples_to_records(
    rows: Iterable[CalibrationReviewExampleRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.to_record() for row in sorted(rows, key=_example_row_sort_key))


def calibration_review_window_summaries_to_records(
    tables: Iterable[CalibrationReviewWindowedTables],
) -> tuple[dict[str, object], ...]:
    return tuple(
        table.to_summary_record()
        for table in sorted(tables, key=_window_table_sort_key)
    )


def write_glyph_review_rows_csv(
    path: Path,
    rows: Iterable[CalibrationGlyphReviewRow],
) -> None:
    _write_csv(
        path, glyph_review_rows_to_records(rows), CALIBRATION_GLYPH_REVIEW_COLUMNS
    )


def write_named_check_review_rows_csv(
    path: Path,
    rows: Iterable[CalibrationNamedCheckReviewRow],
) -> None:
    _write_csv(
        path,
        named_check_review_rows_to_records(rows),
        CALIBRATION_NAMED_CHECK_REVIEW_COLUMNS,
    )


def write_calibration_review_examples_csv(
    path: Path,
    rows: Iterable[CalibrationReviewExampleRow],
) -> None:
    _write_csv(
        path,
        calibration_review_examples_to_records(rows),
        CALIBRATION_REVIEW_EXAMPLE_COLUMNS,
    )


def write_calibration_review_window_summaries_csv(
    path: Path,
    tables: Iterable[CalibrationReviewWindowedTables],
) -> None:
    _write_csv(
        path,
        calibration_review_window_summaries_to_records(tables),
        CALIBRATION_REVIEW_WINDOW_SUMMARY_COLUMNS,
    )


def write_calibration_review_sqlite(
    path: Path,
    *,
    glyph_rows: Iterable[CalibrationGlyphReviewRow],
    named_check_rows: Iterable[CalibrationNamedCheckReviewRow],
    glyph_examples: Iterable[CalibrationReviewExampleRow],
    named_check_examples: Iterable[CalibrationReviewExampleRow],
    windowed_tables: Iterable[CalibrationReviewWindowedTables],
    glyph_rows_table_name: str = CALIBRATION_GLYPH_REVIEW_ROWS_TABLE,
    named_check_rows_table_name: str = CALIBRATION_NAMED_CHECK_REVIEW_ROWS_TABLE,
    glyph_examples_table_name: str = CALIBRATION_GLYPH_REVIEW_EXAMPLES_TABLE,
    named_check_examples_table_name: str = CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_TABLE,
    window_summaries_table_name: str = CALIBRATION_REVIEW_WINDOW_SUMMARIES_TABLE,
) -> None:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    glyph_records = glyph_review_rows_to_records(glyph_rows)
    named_check_records = named_check_review_rows_to_records(named_check_rows)
    glyph_example_records = calibration_review_examples_to_records(glyph_examples)
    named_check_example_records = calibration_review_examples_to_records(
        named_check_examples
    )
    window_summary_records = calibration_review_window_summaries_to_records(
        windowed_tables
    )

    with sqlite3.connect(path) as connection:
        _write_table(
            connection,
            table_name=glyph_rows_table_name,
            columns=CALIBRATION_GLYPH_REVIEW_COLUMNS,
            records=glyph_records,
        )
        _write_table(
            connection,
            table_name=named_check_rows_table_name,
            columns=CALIBRATION_NAMED_CHECK_REVIEW_COLUMNS,
            records=named_check_records,
        )
        _write_table(
            connection,
            table_name=glyph_examples_table_name,
            columns=CALIBRATION_REVIEW_EXAMPLE_COLUMNS,
            records=glyph_example_records,
        )
        _write_table(
            connection,
            table_name=named_check_examples_table_name,
            columns=CALIBRATION_REVIEW_EXAMPLE_COLUMNS,
            records=named_check_example_records,
        )
        _write_table(
            connection,
            table_name=window_summaries_table_name,
            columns=CALIBRATION_REVIEW_WINDOW_SUMMARY_COLUMNS,
            records=window_summary_records,
        )


def sqlite_type_for_calibration_review_column(column: str) -> str:
    if column in {
        "mean_residual",
        "median_residual",
        "mean_abs_residual",
        "forecast_score",
        "realized_current_score",
        "residual",
    }:
        return "REAL"
    if column in {
        "slot",
        "observation_count",
        "min_observation_count",
        "hot_count",
        "cold_count",
        "neutral_count",
        "example_rank",
        "residual_observation_count",
        "glyph_review_row_count",
        "named_check_review_row_count",
        "glyph_example_row_count",
        "named_check_example_row_count",
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
        f"{_quote_identifier(column)} {sqlite_type_for_calibration_review_column(column)}"
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


def _glyph_row_sort_key(row: CalibrationGlyphReviewRow) -> tuple[object, ...]:
    return (
        row.window_label,
        _optional_date_sort_key(row.window_start_date),
        _optional_date_sort_key(row.window_end_date),
        row.horizon,
        row.category,
        row.slot,
        row.glyph,
    )


def _named_check_row_sort_key(
    row: CalibrationNamedCheckReviewRow,
) -> tuple[object, ...]:
    return (
        row.window_label,
        _optional_date_sort_key(row.window_start_date),
        _optional_date_sort_key(row.window_end_date),
        row.horizon,
        row.named_check,
        row.category or "",
        row.slot if row.slot is not None else -1,
        row.glyph or "",
    )


def _example_row_sort_key(row: CalibrationReviewExampleRow) -> tuple[object, ...]:
    return (
        row.window_label,
        _optional_date_sort_key(row.window_start_date),
        _optional_date_sort_key(row.window_end_date),
        row.review_table,
        row.horizon,
        row.category,
        row.slot,
        row.glyph,
        row.named_check,
        row.example_rank,
        row.replay_date.isoformat(),
        row.symbol,
    )


def _window_table_sort_key(
    table: CalibrationReviewWindowedTables,
) -> tuple[str, str, str]:
    return (
        table.window.label,
        _optional_date_sort_key(table.window.start_date),
        _optional_date_sort_key(table.window.end_date),
    )
