from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.residual_attribution_export import (
    RESIDUAL_ATTRIBUTION_ROWS_TABLE,
    RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE,
    write_residual_attribution_rows_csv,
    write_residual_attribution_sqlite,
    write_residual_attribution_summaries_csv,
)
from market_health.calibration.residuals import (
    RESIDUAL_ATTRIBUTION_SCHEMA_VERSION,
    RESIDUAL_ATTRIBUTION_SUMMARY_SCHEMA_VERSION,
    RESIDUAL_COLD,
    RESIDUAL_HOT,
    RESIDUAL_NEUTRAL,
    ResidualAttributionRow,
    ResidualAttributionSummaryRow,
)

RESIDUAL_ATTRIBUTION_ARTIFACT_SCHEMA_VERSION = (
    "calibration_residual_attribution_artifacts.v1"
)
RESIDUAL_ATTRIBUTION_VALIDATION_SUMMARY_SCHEMA_VERSION = (
    "calibration_residual_attribution_validation_summary.v1"
)

RESIDUAL_ATTRIBUTION_ROWS_CSV_FILENAME = "residual_attribution_rows.csv"
RESIDUAL_ATTRIBUTION_SUMMARIES_CSV_FILENAME = "residual_attribution_summaries.csv"
RESIDUAL_ATTRIBUTION_SQLITE_FILENAME = "residual_attribution.sqlite"
RESIDUAL_ATTRIBUTION_VALIDATION_SUMMARY_FILENAME = "validation_summary.json"
RESIDUAL_ATTRIBUTION_MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class ResidualAttributionValidationSummary:
    observation_count: int
    summary_count: int
    replay_dates: tuple[str, ...]
    symbols: tuple[str, ...]
    horizons: tuple[str, ...]
    categories: tuple[str, ...]
    category_slots: tuple[str, ...]
    residual_direction_counts: dict[str, int]
    residual_attribution_run_ids: tuple[str, ...]
    dataset_run_ids: tuple[str, ...]
    schema_versions: tuple[str, ...]
    summary_schema_versions: tuple[str, ...]
    schema_version: str = RESIDUAL_ATTRIBUTION_VALIDATION_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != RESIDUAL_ATTRIBUTION_VALIDATION_SUMMARY_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported residual attribution validation summary schema version: "
                f"{self.schema_version}"
            )
        if self.observation_count < 0:
            raise ValueError(
                "residual attribution observation_count cannot be negative"
            )
        if self.summary_count < 0:
            raise ValueError("residual attribution summary_count cannot be negative")
        for direction in self.residual_direction_counts:
            if direction not in {RESIDUAL_HOT, RESIDUAL_COLD, RESIDUAL_NEUTRAL}:
                raise ValueError(f"unsupported residual direction count: {direction}")

    @property
    def replay_date_count(self) -> int:
        return len(self.replay_dates)

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observation_count": self.observation_count,
            "summary_count": self.summary_count,
            "replay_dates": list(self.replay_dates),
            "replay_date_count": self.replay_date_count,
            "symbols": list(self.symbols),
            "symbol_count": self.symbol_count,
            "horizons": list(self.horizons),
            "categories": list(self.categories),
            "category_slots": list(self.category_slots),
            "residual_direction_counts": dict(self.residual_direction_counts),
            "residual_attribution_run_ids": list(self.residual_attribution_run_ids),
            "dataset_run_ids": list(self.dataset_run_ids),
            "schema_versions": list(self.schema_versions),
            "summary_schema_versions": list(self.summary_schema_versions),
        }


@dataclass(frozen=True)
class ResidualAttributionArtifacts:
    output_dir: Path
    manifest_path: Path
    rows_csv_path: Path
    summaries_csv_path: Path
    sqlite_path: Path
    validation_summary_path: Path
    validation_summary: ResidualAttributionValidationSummary
    rows_table_name: str = RESIDUAL_ATTRIBUTION_ROWS_TABLE
    summaries_table_name: str = RESIDUAL_ATTRIBUTION_SUMMARIES_TABLE
    schema_version: str = RESIDUAL_ATTRIBUTION_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RESIDUAL_ATTRIBUTION_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported residual attribution artifact schema version: "
                f"{self.schema_version}"
            )

    @property
    def observation_count(self) -> int:
        return self.validation_summary.observation_count

    @property
    def summary_count(self) -> int:
        return self.validation_summary.summary_count

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path),
            "rows_csv_path": str(self.rows_csv_path),
            "summaries_csv_path": str(self.summaries_csv_path),
            "sqlite_path": str(self.sqlite_path),
            "validation_summary_path": str(self.validation_summary_path),
            "rows_table_name": self.rows_table_name,
            "summaries_table_name": self.summaries_table_name,
            "observation_count": self.observation_count,
            "summary_count": self.summary_count,
            "validation_summary": self.validation_summary.to_record(),
        }


def residual_attribution_output_dir(
    output_root: Path,
    residual_attribution_run_id: str,
) -> Path:
    return (
        output_root.expanduser()
        / "residual_attribution"
        / _safe_residual_attribution_run_id(residual_attribution_run_id)
    )


def write_residual_attribution_artifacts(
    output_root: Path,
    *,
    rows: tuple[ResidualAttributionRow, ...],
    summaries: tuple[ResidualAttributionSummaryRow, ...],
    residual_attribution_run_id: str = "residual-attribution",
) -> ResidualAttributionArtifacts:
    output_dir = residual_attribution_output_dir(
        output_root, residual_attribution_run_id
    )
    assert_not_live_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_csv_path = output_dir / RESIDUAL_ATTRIBUTION_ROWS_CSV_FILENAME
    summaries_csv_path = output_dir / RESIDUAL_ATTRIBUTION_SUMMARIES_CSV_FILENAME
    sqlite_path = output_dir / RESIDUAL_ATTRIBUTION_SQLITE_FILENAME
    validation_summary_path = (
        output_dir / RESIDUAL_ATTRIBUTION_VALIDATION_SUMMARY_FILENAME
    )
    manifest_path = output_dir / RESIDUAL_ATTRIBUTION_MANIFEST_FILENAME

    write_residual_attribution_rows_csv(rows_csv_path, rows)
    write_residual_attribution_summaries_csv(summaries_csv_path, summaries)
    write_residual_attribution_sqlite(sqlite_path, rows=rows, summaries=summaries)

    validation_summary = build_residual_attribution_validation_summary(rows, summaries)
    artifacts = ResidualAttributionArtifacts(
        output_dir=output_dir,
        manifest_path=manifest_path,
        rows_csv_path=rows_csv_path,
        summaries_csv_path=summaries_csv_path,
        sqlite_path=sqlite_path,
        validation_summary_path=validation_summary_path,
        validation_summary=validation_summary,
    )

    write_residual_attribution_validation_summary_json(
        validation_summary_path,
        validation_summary,
    )
    write_residual_attribution_manifest_json(manifest_path, artifacts)

    return artifacts


def build_residual_attribution_validation_summary(
    rows: tuple[ResidualAttributionRow, ...],
    summaries: tuple[ResidualAttributionSummaryRow, ...],
) -> ResidualAttributionValidationSummary:
    direction_counts = Counter(row.residual_direction for row in rows)

    return ResidualAttributionValidationSummary(
        observation_count=len(rows),
        summary_count=len(summaries),
        replay_dates=tuple(sorted({row.replay_date.isoformat() for row in rows})),
        symbols=tuple(sorted({row.symbol for row in rows})),
        horizons=tuple(sorted({row.horizon for row in rows})),
        categories=tuple(sorted({row.category for row in rows})),
        category_slots=tuple(sorted({row.category_slot for row in rows})),
        residual_direction_counts={
            RESIDUAL_HOT: direction_counts.get(RESIDUAL_HOT, 0),
            RESIDUAL_COLD: direction_counts.get(RESIDUAL_COLD, 0),
            RESIDUAL_NEUTRAL: direction_counts.get(RESIDUAL_NEUTRAL, 0),
        },
        residual_attribution_run_ids=tuple(
            sorted({row.residual_attribution_run_id for row in rows})
        ),
        dataset_run_ids=tuple(sorted({row.dataset_run_id for row in rows})),
        schema_versions=tuple(
            sorted({row.schema_version for row in rows})
            or [RESIDUAL_ATTRIBUTION_SCHEMA_VERSION]
        ),
        summary_schema_versions=tuple(
            sorted({row.schema_version for row in summaries})
            or [RESIDUAL_ATTRIBUTION_SUMMARY_SCHEMA_VERSION]
        ),
    )


def write_residual_attribution_validation_summary_json(
    path: Path,
    validation_summary: ResidualAttributionValidationSummary,
) -> Path:
    _write_json(path, validation_summary.to_record())
    return path


def write_residual_attribution_manifest_json(
    path: Path,
    artifacts: ResidualAttributionArtifacts,
) -> Path:
    _write_json(path, artifacts.to_record())
    return path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _safe_residual_attribution_run_id(value: str) -> str:
    safe = value.strip()
    if not safe:
        raise ValueError("residual attribution run id is required")
    if not all(
        character.isalnum() or character in {"-", "_", "."} for character in safe
    ):
        raise ValueError(f"unsafe residual attribution run id: {value}")
    return safe
