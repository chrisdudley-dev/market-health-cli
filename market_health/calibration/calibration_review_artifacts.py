from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from market_health.calibration.calibration_review import (
    CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION,
    CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION,
    CALIBRATION_REVIEW_EXAMPLE_ROW_SCHEMA_VERSION,
    CALIBRATION_REVIEW_WINDOW_SUMMARY_SCHEMA_VERSION,
    REVIEW_COLD,
    REVIEW_HOT,
    REVIEW_INCONCLUSIVE,
    CalibrationGlyphReviewRow,
    CalibrationNamedCheckReviewRow,
    CalibrationReviewExampleRow,
    CalibrationReviewWindowedTables,
)
from market_health.calibration.calibration_review_export import (
    CALIBRATION_GLYPH_REVIEW_EXAMPLES_TABLE,
    CALIBRATION_GLYPH_REVIEW_ROWS_TABLE,
    CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_TABLE,
    CALIBRATION_NAMED_CHECK_REVIEW_ROWS_TABLE,
    CALIBRATION_REVIEW_WINDOW_SUMMARIES_TABLE,
    write_calibration_review_examples_csv,
    write_calibration_review_sqlite,
    write_calibration_review_window_summaries_csv,
    write_glyph_review_rows_csv,
    write_named_check_review_rows_csv,
)
from market_health.calibration.defaults import assert_not_live_runtime_path

CALIBRATION_REVIEW_ARTIFACT_SCHEMA_VERSION = "calibration_review_artifacts.v1"
CALIBRATION_REVIEW_VALIDATION_SUMMARY_SCHEMA_VERSION = (
    "calibration_review_validation_summary.v1"
)

CALIBRATION_GLYPH_REVIEW_ROWS_CSV_FILENAME = "glyph_review_rows.csv"
CALIBRATION_NAMED_CHECK_REVIEW_ROWS_CSV_FILENAME = "named_check_review_rows.csv"
CALIBRATION_GLYPH_REVIEW_EXAMPLES_CSV_FILENAME = "glyph_review_examples.csv"
CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_CSV_FILENAME = "named_check_review_examples.csv"
CALIBRATION_REVIEW_WINDOW_SUMMARIES_CSV_FILENAME = "window_summaries.csv"
CALIBRATION_REVIEW_SQLITE_FILENAME = "calibration_review.sqlite"
CALIBRATION_REVIEW_VALIDATION_SUMMARY_FILENAME = "validation_summary.json"
CALIBRATION_REVIEW_MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class CalibrationReviewValidationSummary:
    window_count: int
    residual_observation_count: int
    glyph_review_row_count: int
    named_check_review_row_count: int
    glyph_example_row_count: int
    named_check_example_row_count: int
    window_labels: tuple[str, ...]
    residual_attribution_run_ids: tuple[str, ...]
    review_classification_counts: dict[str, int]
    schema_versions: tuple[str, ...]
    schema_version: str = CALIBRATION_REVIEW_VALIDATION_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_REVIEW_VALIDATION_SUMMARY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration review validation summary schema version: "
                f"{self.schema_version}"
            )
        for field_name in (
            "window_count",
            "residual_observation_count",
            "glyph_review_row_count",
            "named_check_review_row_count",
            "glyph_example_row_count",
            "named_check_example_row_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"calibration review {field_name} cannot be negative")
        for classification in self.review_classification_counts:
            if classification not in {REVIEW_HOT, REVIEW_COLD, REVIEW_INCONCLUSIVE}:
                raise ValueError(
                    "unsupported calibration review classification count: "
                    f"{classification}"
                )

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "window_count": self.window_count,
            "residual_observation_count": self.residual_observation_count,
            "glyph_review_row_count": self.glyph_review_row_count,
            "named_check_review_row_count": self.named_check_review_row_count,
            "glyph_example_row_count": self.glyph_example_row_count,
            "named_check_example_row_count": self.named_check_example_row_count,
            "window_labels": list(self.window_labels),
            "residual_attribution_run_ids": list(self.residual_attribution_run_ids),
            "review_classification_counts": dict(self.review_classification_counts),
            "schema_versions": list(self.schema_versions),
        }


@dataclass(frozen=True)
class CalibrationReviewArtifacts:
    output_dir: Path
    manifest_path: Path
    glyph_rows_csv_path: Path
    named_check_rows_csv_path: Path
    glyph_examples_csv_path: Path
    named_check_examples_csv_path: Path
    window_summaries_csv_path: Path
    sqlite_path: Path
    validation_summary_path: Path
    validation_summary: CalibrationReviewValidationSummary
    glyph_rows_table_name: str = CALIBRATION_GLYPH_REVIEW_ROWS_TABLE
    named_check_rows_table_name: str = CALIBRATION_NAMED_CHECK_REVIEW_ROWS_TABLE
    glyph_examples_table_name: str = CALIBRATION_GLYPH_REVIEW_EXAMPLES_TABLE
    named_check_examples_table_name: str = CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_TABLE
    window_summaries_table_name: str = CALIBRATION_REVIEW_WINDOW_SUMMARIES_TABLE
    schema_version: str = CALIBRATION_REVIEW_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_REVIEW_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration review artifact schema version: "
                f"{self.schema_version}"
            )

    @property
    def window_count(self) -> int:
        return self.validation_summary.window_count

    @property
    def residual_observation_count(self) -> int:
        return self.validation_summary.residual_observation_count

    @property
    def glyph_review_row_count(self) -> int:
        return self.validation_summary.glyph_review_row_count

    @property
    def named_check_review_row_count(self) -> int:
        return self.validation_summary.named_check_review_row_count

    @property
    def glyph_example_row_count(self) -> int:
        return self.validation_summary.glyph_example_row_count

    @property
    def named_check_example_row_count(self) -> int:
        return self.validation_summary.named_check_example_row_count

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path),
            "glyph_rows_csv_path": str(self.glyph_rows_csv_path),
            "named_check_rows_csv_path": str(self.named_check_rows_csv_path),
            "glyph_examples_csv_path": str(self.glyph_examples_csv_path),
            "named_check_examples_csv_path": str(self.named_check_examples_csv_path),
            "window_summaries_csv_path": str(self.window_summaries_csv_path),
            "sqlite_path": str(self.sqlite_path),
            "validation_summary_path": str(self.validation_summary_path),
            "glyph_rows_table_name": self.glyph_rows_table_name,
            "named_check_rows_table_name": self.named_check_rows_table_name,
            "glyph_examples_table_name": self.glyph_examples_table_name,
            "named_check_examples_table_name": self.named_check_examples_table_name,
            "window_summaries_table_name": self.window_summaries_table_name,
            "window_count": self.window_count,
            "residual_observation_count": self.residual_observation_count,
            "glyph_review_row_count": self.glyph_review_row_count,
            "named_check_review_row_count": self.named_check_review_row_count,
            "glyph_example_row_count": self.glyph_example_row_count,
            "named_check_example_row_count": self.named_check_example_row_count,
            "validation_summary": self.validation_summary.to_record(),
        }


def calibration_review_output_dir(
    output_root: Path,
    calibration_review_run_id: str,
) -> Path:
    return (
        output_root.expanduser()
        / "calibration_review"
        / _safe_calibration_review_run_id(calibration_review_run_id)
    )


def write_calibration_review_artifacts(
    output_root: Path,
    *,
    windowed_tables: tuple[CalibrationReviewWindowedTables, ...],
    calibration_review_run_id: str = "calibration-review",
) -> CalibrationReviewArtifacts:
    output_dir = calibration_review_output_dir(output_root, calibration_review_run_id)
    assert_not_live_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    glyph_rows = _flatten_glyph_rows(windowed_tables)
    named_check_rows = _flatten_named_check_rows(windowed_tables)
    glyph_examples = _flatten_glyph_examples(windowed_tables)
    named_check_examples = _flatten_named_check_examples(windowed_tables)

    glyph_rows_csv_path = output_dir / CALIBRATION_GLYPH_REVIEW_ROWS_CSV_FILENAME
    named_check_rows_csv_path = (
        output_dir / CALIBRATION_NAMED_CHECK_REVIEW_ROWS_CSV_FILENAME
    )
    glyph_examples_csv_path = (
        output_dir / CALIBRATION_GLYPH_REVIEW_EXAMPLES_CSV_FILENAME
    )
    named_check_examples_csv_path = (
        output_dir / CALIBRATION_NAMED_CHECK_REVIEW_EXAMPLES_CSV_FILENAME
    )
    window_summaries_csv_path = (
        output_dir / CALIBRATION_REVIEW_WINDOW_SUMMARIES_CSV_FILENAME
    )
    sqlite_path = output_dir / CALIBRATION_REVIEW_SQLITE_FILENAME
    validation_summary_path = (
        output_dir / CALIBRATION_REVIEW_VALIDATION_SUMMARY_FILENAME
    )
    manifest_path = output_dir / CALIBRATION_REVIEW_MANIFEST_FILENAME

    write_glyph_review_rows_csv(glyph_rows_csv_path, glyph_rows)
    write_named_check_review_rows_csv(named_check_rows_csv_path, named_check_rows)
    write_calibration_review_examples_csv(glyph_examples_csv_path, glyph_examples)
    write_calibration_review_examples_csv(
        named_check_examples_csv_path,
        named_check_examples,
    )
    write_calibration_review_window_summaries_csv(
        window_summaries_csv_path,
        windowed_tables,
    )
    write_calibration_review_sqlite(
        sqlite_path,
        glyph_rows=glyph_rows,
        named_check_rows=named_check_rows,
        glyph_examples=glyph_examples,
        named_check_examples=named_check_examples,
        windowed_tables=windowed_tables,
    )

    validation_summary = build_calibration_review_validation_summary(windowed_tables)
    artifacts = CalibrationReviewArtifacts(
        output_dir=output_dir,
        manifest_path=manifest_path,
        glyph_rows_csv_path=glyph_rows_csv_path,
        named_check_rows_csv_path=named_check_rows_csv_path,
        glyph_examples_csv_path=glyph_examples_csv_path,
        named_check_examples_csv_path=named_check_examples_csv_path,
        window_summaries_csv_path=window_summaries_csv_path,
        sqlite_path=sqlite_path,
        validation_summary_path=validation_summary_path,
        validation_summary=validation_summary,
    )

    write_calibration_review_validation_summary_json(
        validation_summary_path,
        validation_summary,
    )
    write_calibration_review_manifest_json(manifest_path, artifacts)

    return artifacts


def build_calibration_review_validation_summary(
    windowed_tables: tuple[CalibrationReviewWindowedTables, ...],
) -> CalibrationReviewValidationSummary:
    glyph_rows = _flatten_glyph_rows(windowed_tables)
    named_check_rows = _flatten_named_check_rows(windowed_tables)
    glyph_examples = _flatten_glyph_examples(windowed_tables)
    named_check_examples = _flatten_named_check_examples(windowed_tables)
    classification_counts = Counter(
        row.review_classification for row in (*glyph_rows, *named_check_rows)
    )

    run_ids = sorted(
        {
            table.residual_attribution_run_id
            for table in windowed_tables
            if table.residual_attribution_run_id is not None
        }
    )

    return CalibrationReviewValidationSummary(
        window_count=len(windowed_tables),
        residual_observation_count=sum(
            table.residual_observation_count for table in windowed_tables
        ),
        glyph_review_row_count=len(glyph_rows),
        named_check_review_row_count=len(named_check_rows),
        glyph_example_row_count=len(glyph_examples),
        named_check_example_row_count=len(named_check_examples),
        window_labels=tuple(sorted({table.window.label for table in windowed_tables})),
        residual_attribution_run_ids=tuple(run_ids),
        review_classification_counts={
            REVIEW_HOT: classification_counts.get(REVIEW_HOT, 0),
            REVIEW_COLD: classification_counts.get(REVIEW_COLD, 0),
            REVIEW_INCONCLUSIVE: classification_counts.get(REVIEW_INCONCLUSIVE, 0),
        },
        schema_versions=(
            CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION,
            CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION,
            CALIBRATION_REVIEW_EXAMPLE_ROW_SCHEMA_VERSION,
            CALIBRATION_REVIEW_WINDOW_SUMMARY_SCHEMA_VERSION,
        ),
    )


def write_calibration_review_validation_summary_json(
    path: Path,
    validation_summary: CalibrationReviewValidationSummary,
) -> Path:
    _write_json(path, validation_summary.to_record())
    return path


def write_calibration_review_manifest_json(
    path: Path,
    artifacts: CalibrationReviewArtifacts,
) -> Path:
    _write_json(path, artifacts.to_record())
    return path


def _flatten_glyph_rows(
    windowed_tables: tuple[CalibrationReviewWindowedTables, ...],
) -> tuple[CalibrationGlyphReviewRow, ...]:
    return tuple(row for table in windowed_tables for row in table.glyph_review_rows)


def _flatten_named_check_rows(
    windowed_tables: tuple[CalibrationReviewWindowedTables, ...],
) -> tuple[CalibrationNamedCheckReviewRow, ...]:
    return tuple(
        row for table in windowed_tables for row in table.named_check_review_rows
    )


def _flatten_glyph_examples(
    windowed_tables: tuple[CalibrationReviewWindowedTables, ...],
) -> tuple[CalibrationReviewExampleRow, ...]:
    return tuple(row for table in windowed_tables for row in table.glyph_example_rows)


def _flatten_named_check_examples(
    windowed_tables: tuple[CalibrationReviewWindowedTables, ...],
) -> tuple[CalibrationReviewExampleRow, ...]:
    return tuple(
        row for table in windowed_tables for row in table.named_check_example_rows
    )


def _safe_calibration_review_run_id(value: str) -> str:
    if not value or "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"unsafe calibration review run id: {value}")
    return value


def _write_json(path: Path, payload: dict[str, object]) -> None:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
