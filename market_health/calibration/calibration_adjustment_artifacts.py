from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from market_health.calibration.calibration_adjustment_export import (
    CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE,
    CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE,
    CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE,
    write_calibration_adjustment_candidates_csv,
    write_calibration_dry_run_comparison_rows_csv,
    write_calibration_dry_run_simulation_rows_csv,
    write_calibration_dry_run_sqlite,
)
from market_health.calibration.calibration_adjustments import (
    CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION,
    CALIBRATION_DRY_RUN_COMPARISON_SCHEMA_VERSION,
    CALIBRATION_DRY_RUN_SIMULATION_SCHEMA_VERSION,
    CalibrationAdjustmentCandidateRow,
    CalibrationDryRunComparisonRow,
    CalibrationDryRunSimulationRow,
)
from market_health.calibration.check_output import (
    REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION,
    ReviewedCheckScoreCalibrationAdjustment,
)
from market_health.calibration.defaults import assert_not_live_runtime_path

CALIBRATION_DRY_RUN_ARTIFACT_SCHEMA_VERSION = "calibration_dry_run_artifacts.v1"
CALIBRATION_DRY_RUN_VALIDATION_SUMMARY_SCHEMA_VERSION = (
    "calibration_dry_run_validation_summary.v1"
)

CALIBRATION_ADJUSTMENT_CANDIDATES_CSV_FILENAME = "adjustment_candidates.csv"
CALIBRATION_DRY_RUN_SIMULATION_ROWS_CSV_FILENAME = "dry_run_simulation_rows.csv"
CALIBRATION_DRY_RUN_COMPARISON_ROWS_CSV_FILENAME = "dry_run_comparison_rows.csv"
CALIBRATION_DRY_RUN_SQLITE_FILENAME = "calibration_dry_run.sqlite"
CALIBRATION_DRY_RUN_VALIDATION_SUMMARY_FILENAME = "validation_summary.json"
CALIBRATION_DRY_RUN_MANIFEST_FILENAME = "manifest.json"
CALIBRATION_REVIEWED_CHECK_SCORE_ADJUSTMENTS_FILENAME = (
    "reviewed_check_score_adjustments.json"
)


@dataclass(frozen=True)
class CalibrationDryRunValidationSummary:
    candidate_count: int
    simulation_row_count: int
    comparison_row_count: int
    unique_applied_candidate_count: int
    reviewed_check_score_adjustment_count: int
    symbols: tuple[str, ...]
    horizons: tuple[str, ...]
    category_slots: tuple[str, ...]
    candidate_scope_counts: dict[str, int]
    comparison_group_counts: dict[str, int]
    residual_attribution_run_ids: tuple[str, ...]
    calibration_review_run_ids: tuple[str, ...]
    dry_run_simulation_run_ids: tuple[str, ...]
    candidate_schema_versions: tuple[str, ...]
    simulation_schema_versions: tuple[str, ...]
    comparison_schema_versions: tuple[str, ...]
    reviewed_check_score_adjustment_category_slots: tuple[str, ...]
    reviewed_check_score_adjustment_schema_versions: tuple[str, ...]
    schema_version: str = CALIBRATION_DRY_RUN_VALIDATION_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_DRY_RUN_VALIDATION_SUMMARY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration dry-run validation summary schema version: "
                f"{self.schema_version}"
            )
        for field_name in (
            "candidate_count",
            "simulation_row_count",
            "comparison_row_count",
            "unique_applied_candidate_count",
            "reviewed_check_score_adjustment_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"calibration dry-run {field_name} cannot be negative")

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_count": self.candidate_count,
            "simulation_row_count": self.simulation_row_count,
            "comparison_row_count": self.comparison_row_count,
            "unique_applied_candidate_count": self.unique_applied_candidate_count,
            "reviewed_check_score_adjustment_count": (
                self.reviewed_check_score_adjustment_count
            ),
            "symbols": list(self.symbols),
            "symbol_count": self.symbol_count,
            "horizons": list(self.horizons),
            "category_slots": list(self.category_slots),
            "candidate_scope_counts": dict(self.candidate_scope_counts),
            "comparison_group_counts": dict(self.comparison_group_counts),
            "residual_attribution_run_ids": list(self.residual_attribution_run_ids),
            "calibration_review_run_ids": list(self.calibration_review_run_ids),
            "dry_run_simulation_run_ids": list(self.dry_run_simulation_run_ids),
            "candidate_schema_versions": list(self.candidate_schema_versions),
            "simulation_schema_versions": list(self.simulation_schema_versions),
            "comparison_schema_versions": list(self.comparison_schema_versions),
            "reviewed_check_score_adjustment_category_slots": list(
                self.reviewed_check_score_adjustment_category_slots
            ),
            "reviewed_check_score_adjustment_schema_versions": list(
                self.reviewed_check_score_adjustment_schema_versions
            ),
        }


@dataclass(frozen=True)
class CalibrationDryRunArtifacts:
    output_dir: Path
    manifest_path: Path
    candidates_csv_path: Path
    simulation_rows_csv_path: Path
    comparison_rows_csv_path: Path
    sqlite_path: Path
    validation_summary_path: Path
    reviewed_check_score_adjustments_path: Path
    validation_summary: CalibrationDryRunValidationSummary
    candidates_table_name: str = CALIBRATION_ADJUSTMENT_CANDIDATES_TABLE
    simulation_rows_table_name: str = CALIBRATION_DRY_RUN_SIMULATION_ROWS_TABLE
    comparison_rows_table_name: str = CALIBRATION_DRY_RUN_COMPARISON_ROWS_TABLE
    schema_version: str = CALIBRATION_DRY_RUN_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_DRY_RUN_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration dry-run artifact schema version: "
                f"{self.schema_version}"
            )

    @property
    def candidate_count(self) -> int:
        return self.validation_summary.candidate_count

    @property
    def simulation_row_count(self) -> int:
        return self.validation_summary.simulation_row_count

    @property
    def comparison_row_count(self) -> int:
        return self.validation_summary.comparison_row_count

    @property
    def reviewed_check_score_adjustment_count(self) -> int:
        return self.validation_summary.reviewed_check_score_adjustment_count

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path),
            "candidates_csv_path": str(self.candidates_csv_path),
            "simulation_rows_csv_path": str(self.simulation_rows_csv_path),
            "comparison_rows_csv_path": str(self.comparison_rows_csv_path),
            "sqlite_path": str(self.sqlite_path),
            "validation_summary_path": str(self.validation_summary_path),
            "reviewed_check_score_adjustments_path": str(
                self.reviewed_check_score_adjustments_path
            ),
            "candidates_table_name": self.candidates_table_name,
            "simulation_rows_table_name": self.simulation_rows_table_name,
            "comparison_rows_table_name": self.comparison_rows_table_name,
            "candidate_count": self.candidate_count,
            "simulation_row_count": self.simulation_row_count,
            "comparison_row_count": self.comparison_row_count,
            "reviewed_check_score_adjustment_count": (
                self.reviewed_check_score_adjustment_count
            ),
            "validation_summary": self.validation_summary.to_record(),
        }


def calibration_dry_run_output_dir(
    output_root: Path,
    dry_run_simulation_run_id: str,
) -> Path:
    return (
        output_root.expanduser()
        / "calibration_dry_run"
        / _safe_dry_run_simulation_run_id(dry_run_simulation_run_id)
    )


def write_calibration_dry_run_artifacts(
    output_root: Path,
    *,
    candidates: tuple[CalibrationAdjustmentCandidateRow, ...],
    simulation_rows: tuple[CalibrationDryRunSimulationRow, ...],
    comparison_rows: tuple[CalibrationDryRunComparisonRow, ...],
    reviewed_check_score_adjustments: tuple[
        ReviewedCheckScoreCalibrationAdjustment, ...
    ] = (),
    dry_run_simulation_run_id: str = "calibration-dry-run",
) -> CalibrationDryRunArtifacts:
    output_dir = calibration_dry_run_output_dir(
        output_root,
        dry_run_simulation_run_id,
    )
    assert_not_live_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates_csv_path = output_dir / CALIBRATION_ADJUSTMENT_CANDIDATES_CSV_FILENAME
    simulation_rows_csv_path = (
        output_dir / CALIBRATION_DRY_RUN_SIMULATION_ROWS_CSV_FILENAME
    )
    comparison_rows_csv_path = (
        output_dir / CALIBRATION_DRY_RUN_COMPARISON_ROWS_CSV_FILENAME
    )
    sqlite_path = output_dir / CALIBRATION_DRY_RUN_SQLITE_FILENAME
    validation_summary_path = (
        output_dir / CALIBRATION_DRY_RUN_VALIDATION_SUMMARY_FILENAME
    )
    manifest_path = output_dir / CALIBRATION_DRY_RUN_MANIFEST_FILENAME
    reviewed_check_score_adjustments_path = (
        output_dir / CALIBRATION_REVIEWED_CHECK_SCORE_ADJUSTMENTS_FILENAME
    )

    write_calibration_adjustment_candidates_csv(candidates_csv_path, candidates)
    write_calibration_dry_run_simulation_rows_csv(
        simulation_rows_csv_path,
        simulation_rows,
    )
    write_calibration_dry_run_comparison_rows_csv(
        comparison_rows_csv_path,
        comparison_rows,
    )
    write_calibration_dry_run_sqlite(
        sqlite_path,
        candidates=candidates,
        simulation_rows=simulation_rows,
        comparison_rows=comparison_rows,
    )

    write_reviewed_check_score_adjustments_json(
        reviewed_check_score_adjustments_path,
        reviewed_check_score_adjustments,
    )

    validation_summary = build_calibration_dry_run_validation_summary(
        candidates,
        simulation_rows,
        comparison_rows,
        reviewed_check_score_adjustments=reviewed_check_score_adjustments,
    )
    artifacts = CalibrationDryRunArtifacts(
        output_dir=output_dir,
        manifest_path=manifest_path,
        candidates_csv_path=candidates_csv_path,
        simulation_rows_csv_path=simulation_rows_csv_path,
        comparison_rows_csv_path=comparison_rows_csv_path,
        sqlite_path=sqlite_path,
        validation_summary_path=validation_summary_path,
        reviewed_check_score_adjustments_path=reviewed_check_score_adjustments_path,
        validation_summary=validation_summary,
    )

    write_calibration_dry_run_validation_summary_json(
        validation_summary_path,
        validation_summary,
    )
    write_calibration_dry_run_manifest_json(manifest_path, artifacts)

    return artifacts


def build_calibration_dry_run_validation_summary(
    candidates: tuple[CalibrationAdjustmentCandidateRow, ...],
    simulation_rows: tuple[CalibrationDryRunSimulationRow, ...],
    comparison_rows: tuple[CalibrationDryRunComparisonRow, ...],
    reviewed_check_score_adjustments: tuple[
        ReviewedCheckScoreCalibrationAdjustment, ...
    ] = (),
) -> CalibrationDryRunValidationSummary:
    candidate_scope_counts = Counter(row.candidate_scope for row in candidates)
    comparison_group_counts = Counter(row.group_name for row in comparison_rows)
    applied_candidate_ids = sorted(
        {
            candidate_id
            for row in simulation_rows
            for candidate_id in row.applied_candidate_ids
        }
    )

    return CalibrationDryRunValidationSummary(
        candidate_count=len(candidates),
        simulation_row_count=len(simulation_rows),
        comparison_row_count=len(comparison_rows),
        unique_applied_candidate_count=len(applied_candidate_ids),
        reviewed_check_score_adjustment_count=len(reviewed_check_score_adjustments),
        symbols=tuple(sorted({row.symbol for row in simulation_rows})),
        horizons=tuple(sorted({row.horizon for row in simulation_rows})),
        category_slots=tuple(sorted({row.category_slot for row in simulation_rows})),
        candidate_scope_counts=dict(sorted(candidate_scope_counts.items())),
        comparison_group_counts=dict(sorted(comparison_group_counts.items())),
        residual_attribution_run_ids=tuple(
            sorted({row.residual_attribution_run_id for row in simulation_rows})
        ),
        calibration_review_run_ids=tuple(
            sorted({row.calibration_review_run_id for row in simulation_rows})
        ),
        dry_run_simulation_run_ids=tuple(
            sorted({row.dry_run_simulation_run_id for row in simulation_rows})
        ),
        candidate_schema_versions=tuple(
            sorted({row.schema_version for row in candidates})
            or [CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION]
        ),
        simulation_schema_versions=tuple(
            sorted({row.schema_version for row in simulation_rows})
            or [CALIBRATION_DRY_RUN_SIMULATION_SCHEMA_VERSION]
        ),
        comparison_schema_versions=tuple(
            sorted({row.schema_version for row in comparison_rows})
            or [CALIBRATION_DRY_RUN_COMPARISON_SCHEMA_VERSION]
        ),
        reviewed_check_score_adjustment_category_slots=tuple(
            sorted({row.category_slot for row in reviewed_check_score_adjustments})
        ),
        reviewed_check_score_adjustment_schema_versions=tuple(
            sorted({row.schema_version for row in reviewed_check_score_adjustments})
            or [REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION]
        ),
    )


def write_reviewed_check_score_adjustments_json(
    path: Path,
    reviewed_check_score_adjustments: tuple[
        ReviewedCheckScoreCalibrationAdjustment, ...
    ],
) -> Path:
    _write_json(
        path,
        {
            "schema_version": (
                REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION
            ),
            "row_count": len(reviewed_check_score_adjustments),
            "rows": [
                adjustment.to_record()
                for adjustment in reviewed_check_score_adjustments
            ],
        },
    )
    return path


def write_calibration_dry_run_validation_summary_json(
    path: Path,
    validation_summary: CalibrationDryRunValidationSummary,
) -> Path:
    _write_json(path, validation_summary.to_record())
    return path


def write_calibration_dry_run_manifest_json(
    path: Path,
    artifacts: CalibrationDryRunArtifacts,
) -> Path:
    _write_json(path, artifacts.to_record())
    return path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_dry_run_simulation_run_id(value: str) -> str:
    safe = value.strip()
    if not safe:
        raise ValueError("calibration dry-run simulation run id is required")
    if not all(
        character.isalnum() or character in {"-", "_", "."} for character in safe
    ):
        raise ValueError(f"unsafe calibration dry-run simulation run id: {value}")
    return safe
