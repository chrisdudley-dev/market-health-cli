from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_health.calibration.check_output import (
    REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION,
    ReviewedCheckScoreCalibrationAdjustment,
)
from market_health.calibration.defaults import assert_not_live_runtime_path


def reviewed_check_score_adjustments_to_records(
    adjustments: tuple[ReviewedCheckScoreCalibrationAdjustment, ...],
) -> list[dict[str, object]]:
    return [adjustment.to_record() for adjustment in adjustments]


def reviewed_check_score_adjustments_payload(
    adjustments: tuple[ReviewedCheckScoreCalibrationAdjustment, ...],
) -> dict[str, object]:
    return {
        "schema_version": REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION,
        "row_count": len(adjustments),
        "rows": reviewed_check_score_adjustments_to_records(adjustments),
    }


def write_reviewed_check_score_adjustments_json(
    path: Path,
    adjustments: tuple[ReviewedCheckScoreCalibrationAdjustment, ...],
) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            reviewed_check_score_adjustments_payload(adjustments),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def read_reviewed_check_score_adjustments_json(
    path: Path,
) -> tuple[ReviewedCheckScoreCalibrationAdjustment, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("reviewed check score adjustment payload must be an object")

    schema_version = payload.get("schema_version")
    if schema_version != REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported reviewed check score adjustment payload schema version: "
            f"{schema_version}"
        )

    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("reviewed check score adjustment payload rows must be a list")

    row_count = payload.get("row_count")
    if row_count != len(rows):
        raise ValueError(
            "reviewed check score adjustment payload row_count does not match rows"
        )

    adjustments = tuple(_adjustment_from_record(row) for row in rows)
    _validate_unique_scopes(adjustments)
    return adjustments


def _adjustment_from_record(
    record: Any,
) -> ReviewedCheckScoreCalibrationAdjustment:
    if not isinstance(record, dict):
        raise ValueError("reviewed check score adjustment row must be an object")

    return ReviewedCheckScoreCalibrationAdjustment(
        schema_version=str(record.get("schema_version", "")),
        horizon=str(record.get("horizon", "")),
        category=str(record.get("category", "")),
        slot=_int_field(record, "slot"),
        score_delta=_float_field(record, "score_delta"),
        calibration_review_run_id=str(record.get("calibration_review_run_id", "")),
        dry_run_simulation_run_id=str(record.get("dry_run_simulation_run_id", "")),
        approved_by=str(record.get("approved_by", "")),
        rationale=str(record.get("rationale", "")),
    )


def _int_field(record: dict[str, Any], field_name: str) -> int:
    try:
        value = int(record[field_name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"reviewed check score adjustment {field_name} must be an integer"
        ) from exc
    return value


def _float_field(record: dict[str, Any], field_name: str) -> float:
    try:
        value = float(record[field_name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"reviewed check score adjustment {field_name} must be numeric"
        ) from exc
    return value


def _validate_unique_scopes(
    adjustments: tuple[ReviewedCheckScoreCalibrationAdjustment, ...],
) -> None:
    scopes = {
        (adjustment.horizon, adjustment.category, adjustment.slot)
        for adjustment in adjustments
    }
    if len(scopes) != len(adjustments):
        raise ValueError(
            "reviewed check score adjustment payload contains duplicate "
            "horizon/category/slot scopes"
        )
