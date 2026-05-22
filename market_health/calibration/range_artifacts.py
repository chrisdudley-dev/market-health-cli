from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Mapping

from market_health.calibration.check_output import (
    CheckReplayRow,
    build_fixture_check_replay_rows,
)
from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.range_runner import RangeReplayResult
from market_health.calibration.single_date_artifacts import (
    SingleDateReplayArtifacts,
    write_single_date_replay_artifacts,
)
from market_health.calibration.single_date_replay import SingleDateReplayResult

RANGE_REPLAY_ARTIFACT_SCHEMA_VERSION = "calibration_range_replay_artifacts.v1"
RANGE_REPLAY_MANIFEST_FILENAME = "range_manifest.json"


@dataclass(frozen=True)
class RangeReplayArtifacts:
    output_dir: Path
    manifest_path: Path
    single_date_artifacts: tuple[SingleDateReplayArtifacts, ...]
    schema_version: str = RANGE_REPLAY_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RANGE_REPLAY_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported range replay artifact schema version: {self.schema_version}"
            )

    @property
    def date_count(self) -> int:
        return len(self.single_date_artifacts)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path),
            "date_count": self.date_count,
            "single_date_artifacts": [
                artifact.to_record() for artifact in self.single_date_artifacts
            ],
        }


def range_replay_output_dir(
    output_root: Path,
    range_result: RangeReplayResult,
) -> Path:
    request = range_result.request
    range_name = f"{request.start_date.isoformat()}_to_{request.end_date.isoformat()}"
    return output_root / "range_replay" / range_name


def write_range_replay_artifacts(
    *,
    output_root: Path,
    range_result: RangeReplayResult,
    check_rows_by_date: Mapping[date, Iterable[CheckReplayRow]] | None = None,
) -> RangeReplayArtifacts:
    assert_not_live_runtime_path(output_root)

    output_dir = range_replay_output_dir(output_root, range_result)
    assert_not_live_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    single_date_artifacts = tuple(
        write_single_date_replay_artifacts(
            output_root=output_dir,
            replay_result=result,
            check_rows=_check_rows_for_result(
                result,
                check_rows_by_date=check_rows_by_date,
            ),
        )
        for result in range_result.results
    )

    artifacts = RangeReplayArtifacts(
        output_dir=output_dir,
        manifest_path=output_dir / RANGE_REPLAY_MANIFEST_FILENAME,
        single_date_artifacts=single_date_artifacts,
    )
    write_range_manifest_json(artifacts.manifest_path, range_result, artifacts)
    return artifacts


def write_range_manifest_json(
    path: Path,
    range_result: RangeReplayResult,
    artifacts: RangeReplayArtifacts,
) -> Path:
    payload = {
        "schema_version": RANGE_REPLAY_ARTIFACT_SCHEMA_VERSION,
        "range_replay": range_result.to_record(),
        "artifacts": artifacts.to_record(),
    }
    return _write_json(path, payload)


def _check_rows_for_result(
    result: SingleDateReplayResult,
    *,
    check_rows_by_date: Mapping[date, Iterable[CheckReplayRow]] | None,
) -> tuple[CheckReplayRow, ...]:
    if check_rows_by_date is not None:
        return tuple(check_rows_by_date.get(result.replay_date, ()))

    eligible_symbols = result.asof_input_record.get("eligible_symbols")
    if isinstance(eligible_symbols, list | tuple):
        symbols = tuple(str(symbol) for symbol in eligible_symbols)
    else:
        symbols = tuple(row.symbol for row in result.rows)

    return build_fixture_check_replay_rows(
        replay_date=result.replay_date,
        symbols=symbols,
    )


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
