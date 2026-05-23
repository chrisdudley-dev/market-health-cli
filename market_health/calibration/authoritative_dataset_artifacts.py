from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Mapping

from market_health.calibration.authoritative_dataset import (
    REALIZED_OUTCOME_STATUSES,
    VALID_HORIZONS,
    AuthoritativeReplayDatasetRow,
)
from market_health.calibration.authoritative_dataset_export import (
    AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE,
    write_authoritative_dataset_rows_csv,
    write_authoritative_dataset_rows_sqlite,
)
from market_health.calibration.defaults import assert_not_live_runtime_path

AUTHORITATIVE_DATASET_ARTIFACT_SCHEMA_VERSION = (
    "calibration_authoritative_dataset_artifacts.v1"
)
AUTHORITATIVE_DATASET_VALIDATION_SUMMARY_SCHEMA_VERSION = (
    "calibration_authoritative_dataset_validation_summary.v1"
)

AUTHORITATIVE_DATASET_CSV_FILENAME = "authoritative_replay_dataset.csv"
AUTHORITATIVE_DATASET_SQLITE_FILENAME = "authoritative_replay_dataset.sqlite"
AUTHORITATIVE_DATASET_VALIDATION_SUMMARY_FILENAME = "validation_summary.json"
AUTHORITATIVE_DATASET_MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class AuthoritativeDatasetValidationSummary:
    row_count: int
    replay_dates: tuple[date, ...]
    symbols: tuple[str, ...]
    horizons: tuple[str, ...]
    realized_outcome_status_counts: Mapping[str, int]
    dataset_run_ids: tuple[str, ...]
    schema_versions: tuple[str, ...]
    schema_version: str = AUTHORITATIVE_DATASET_VALIDATION_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != AUTHORITATIVE_DATASET_VALIDATION_SUMMARY_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported authoritative dataset validation summary schema "
                f"version: {self.schema_version}"
            )
        if self.row_count < 0:
            raise ValueError("authoritative dataset row_count must be non-negative")
        for status in self.realized_outcome_status_counts:
            if status not in REALIZED_OUTCOME_STATUSES:
                raise ValueError(f"unsupported realized outcome status: {status}")
        for horizon in self.horizons:
            if horizon not in VALID_HORIZONS:
                raise ValueError(
                    f"unsupported authoritative dataset horizon: {horizon}"
                )

    @property
    def replay_date_count(self) -> int:
        return len(self.replay_dates)

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "row_count": self.row_count,
            "replay_date_count": self.replay_date_count,
            "replay_dates": [item.isoformat() for item in self.replay_dates],
            "symbol_count": self.symbol_count,
            "symbols": list(self.symbols),
            "horizons": list(self.horizons),
            "realized_outcome_status_counts": dict(
                sorted(self.realized_outcome_status_counts.items())
            ),
            "dataset_run_ids": list(self.dataset_run_ids),
            "schema_versions": list(self.schema_versions),
        }


@dataclass(frozen=True)
class AuthoritativeDatasetArtifacts:
    output_dir: Path
    manifest_path: Path
    dataset_csv_path: Path
    dataset_sqlite_path: Path
    validation_summary_path: Path
    validation_summary: AuthoritativeDatasetValidationSummary
    sqlite_table_name: str = AUTHORITATIVE_REPLAY_DATASET_ROWS_TABLE
    schema_version: str = AUTHORITATIVE_DATASET_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AUTHORITATIVE_DATASET_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported authoritative dataset artifact schema version: "
                f"{self.schema_version}"
            )

    @property
    def row_count(self) -> int:
        return self.validation_summary.row_count

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path),
            "dataset_csv_path": str(self.dataset_csv_path),
            "dataset_sqlite_path": str(self.dataset_sqlite_path),
            "validation_summary_path": str(self.validation_summary_path),
            "sqlite_table_name": self.sqlite_table_name,
            "row_count": self.row_count,
            "validation_summary": self.validation_summary.to_record(),
        }


def build_authoritative_dataset_validation_summary(
    rows: Iterable[AuthoritativeReplayDatasetRow],
) -> AuthoritativeDatasetValidationSummary:
    row_tuple = tuple(rows)
    return AuthoritativeDatasetValidationSummary(
        row_count=len(row_tuple),
        replay_dates=tuple(sorted({row.replay_date for row in row_tuple})),
        symbols=tuple(sorted({row.symbol for row in row_tuple})),
        horizons=tuple(sorted({row.horizon for row in row_tuple})),
        realized_outcome_status_counts=_realized_outcome_status_counts(row_tuple),
        dataset_run_ids=tuple(sorted({row.dataset_run_id for row in row_tuple})),
        schema_versions=tuple(sorted({row.schema_version for row in row_tuple})),
    )


def authoritative_dataset_output_dir(
    output_root: Path,
    dataset_run_id: str,
) -> Path:
    return output_root / "authoritative_dataset" / _safe_dataset_run_id(dataset_run_id)


def write_authoritative_dataset_artifacts(
    *,
    output_root: Path,
    rows: Iterable[AuthoritativeReplayDatasetRow],
    dataset_run_id: str = "authoritative-replay-dataset",
) -> AuthoritativeDatasetArtifacts:
    assert_not_live_runtime_path(output_root)

    row_tuple = tuple(rows)
    output_dir = authoritative_dataset_output_dir(output_root, dataset_run_id)
    assert_not_live_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_csv_path = write_authoritative_dataset_rows_csv(
        output_dir / AUTHORITATIVE_DATASET_CSV_FILENAME,
        row_tuple,
    )
    dataset_sqlite_path = write_authoritative_dataset_rows_sqlite(
        output_dir / AUTHORITATIVE_DATASET_SQLITE_FILENAME,
        row_tuple,
    )
    validation_summary = build_authoritative_dataset_validation_summary(row_tuple)
    validation_summary_path = write_authoritative_dataset_validation_summary_json(
        output_dir / AUTHORITATIVE_DATASET_VALIDATION_SUMMARY_FILENAME,
        validation_summary,
    )

    artifacts = AuthoritativeDatasetArtifacts(
        output_dir=output_dir,
        manifest_path=output_dir / AUTHORITATIVE_DATASET_MANIFEST_FILENAME,
        dataset_csv_path=dataset_csv_path,
        dataset_sqlite_path=dataset_sqlite_path,
        validation_summary_path=validation_summary_path,
        validation_summary=validation_summary,
    )
    write_authoritative_dataset_manifest_json(artifacts.manifest_path, artifacts)
    return artifacts


def write_authoritative_dataset_validation_summary_json(
    path: Path,
    summary: AuthoritativeDatasetValidationSummary,
) -> Path:
    return _write_json(path, summary.to_record())


def write_authoritative_dataset_manifest_json(
    path: Path,
    artifacts: AuthoritativeDatasetArtifacts,
) -> Path:
    payload = {
        "schema_version": AUTHORITATIVE_DATASET_ARTIFACT_SCHEMA_VERSION,
        "artifacts": artifacts.to_record(),
    }
    return _write_json(path, payload)


def _realized_outcome_status_counts(
    rows: tuple[AuthoritativeReplayDatasetRow, ...],
) -> dict[str, int]:
    counter = Counter(row.realized_outcome_status for row in rows)
    return {status: counter.get(status, 0) for status in REALIZED_OUTCOME_STATUSES}


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    temp_path.replace(path)
    return path


def _safe_dataset_run_id(dataset_run_id: str) -> str:
    value = dataset_run_id.strip()
    if not value:
        raise ValueError("authoritative dataset_run_id is required")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(character not in allowed for character in value):
        raise ValueError(
            "authoritative dataset_run_id may only contain letters, numbers, "
            "dots, underscores, and hyphens"
        )
    return value
