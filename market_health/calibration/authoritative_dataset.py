from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from market_health.calibration.check_inventory import REPLAYABILITY_CLASSES
from market_health.calibration.check_output import (
    CHECK_REPLAY_ROW_SCHEMA_VERSION,
    MEASUREMENT_STATUSES,
    VALID_HORIZONS,
)
from market_health.calibration.range_runner import RANGE_REPLAY_RESULT_SCHEMA_VERSION
from market_health.calibration.single_date_replay import (
    SINGLE_DATE_REPLAY_SCHEMA_VERSION,
)

AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION = (
    "calibration_authoritative_replay_dataset.v1"
)

REALIZED_OUTCOME_AVAILABLE = "available"
REALIZED_OUTCOME_MISSING = "missing"
REALIZED_OUTCOME_NOT_APPLICABLE = "not_applicable"

REALIZED_OUTCOME_STATUSES = (
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_MISSING,
    REALIZED_OUTCOME_NOT_APPLICABLE,
)

AUTHORITATIVE_REPLAY_DATASET_COLUMNS = (
    "schema_version",
    "replay_date",
    "symbol",
    "current_score",
    "h1_score",
    "h5_score",
    "blend_score",
    "state",
    "horizon",
    "target_date",
    "realized_current_score",
    "realized_return",
    "realized_outcome_status",
    "category",
    "slot",
    "category_slot",
    "glyph",
    "named_check",
    "check_score",
    "replayability_class",
    "measurement_status",
    "source_module",
    "function_name",
    "replay_row_schema_version",
    "check_row_schema_version",
    "single_date_replay_schema_version",
    "range_replay_schema_version",
    "audit_token",
    "dataset_run_id",
)


@dataclass(frozen=True)
class AuthoritativeReplayDatasetRow:
    replay_date: date
    symbol: str
    current_score: float
    h1_score: float
    h5_score: float
    blend_score: float
    state: str
    horizon: str
    category: str
    slot: int
    glyph: str
    named_check: str
    check_score: float
    replayability_class: str
    measurement_status: str
    source_module: str
    function_name: str
    audit_token: str
    target_date: date | None = None
    realized_current_score: float | None = None
    realized_return: float | None = None
    realized_outcome_status: str = REALIZED_OUTCOME_NOT_APPLICABLE
    replay_row_schema_version: str = "calibration_replay_artifact_row.v1"
    check_row_schema_version: str = CHECK_REPLAY_ROW_SCHEMA_VERSION
    single_date_replay_schema_version: str = SINGLE_DATE_REPLAY_SCHEMA_VERSION
    range_replay_schema_version: str = RANGE_REPLAY_RESULT_SCHEMA_VERSION
    dataset_run_id: str = "authoritative-replay-dataset"
    schema_version: str = AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION:
            raise ValueError(
                "unsupported authoritative replay dataset schema version: "
                f"{self.schema_version}"
            )

        symbol = self.symbol.strip().upper()
        category = self.category.strip().upper()
        horizon = self.horizon.strip().upper()
        state = self.state.strip().upper()

        if not symbol:
            raise ValueError("authoritative replay dataset row symbol is required")
        if category not in {"A", "B", "C", "D", "E"}:
            raise ValueError(f"unsupported check category: {self.category}")
        if not 1 <= self.slot <= 6:
            raise ValueError(f"unsupported check slot: {self.slot}")
        if horizon not in VALID_HORIZONS:
            raise ValueError(f"unsupported dataset horizon: {self.horizon}")
        if not state:
            raise ValueError("authoritative replay dataset row state is required")
        if self.replayability_class not in REPLAYABILITY_CLASSES:
            raise ValueError(
                f"unsupported replayability class: {self.replayability_class}"
            )
        if self.measurement_status not in MEASUREMENT_STATUSES:
            raise ValueError(
                f"unsupported measurement status: {self.measurement_status}"
            )
        if self.realized_outcome_status not in REALIZED_OUTCOME_STATUSES:
            raise ValueError(
                f"unsupported realized outcome status: {self.realized_outcome_status}"
            )

        if self.realized_outcome_status == REALIZED_OUTCOME_AVAILABLE:
            if self.target_date is None:
                raise ValueError("available realized outcome requires target_date")
            if self.realized_current_score is None:
                raise ValueError(
                    "available realized outcome requires realized_current_score"
                )
            if self.realized_return is None:
                raise ValueError("available realized outcome requires realized_return")

        if self.realized_outcome_status == REALIZED_OUTCOME_NOT_APPLICABLE:
            if self.target_date is not None:
                raise ValueError(
                    "not_applicable realized outcome cannot set target_date"
                )
            if self.realized_current_score is not None:
                raise ValueError(
                    "not_applicable realized outcome cannot set realized_current_score"
                )
            if self.realized_return is not None:
                raise ValueError(
                    "not_applicable realized outcome cannot set realized_return"
                )

        for field_name in (
            "glyph",
            "named_check",
            "source_module",
            "function_name",
            "audit_token",
            "replay_row_schema_version",
            "check_row_schema_version",
            "single_date_replay_schema_version",
            "range_replay_schema_version",
            "dataset_run_id",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"authoritative dataset {field_name} is required")

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "state", state)

    @property
    def category_slot(self) -> str:
        return f"{self.category}{self.slot}"

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "symbol": self.symbol,
            "current_score": self.current_score,
            "h1_score": self.h1_score,
            "h5_score": self.h5_score,
            "blend_score": self.blend_score,
            "state": self.state,
            "horizon": self.horizon,
            "target_date": _optional_date(self.target_date),
            "realized_current_score": self.realized_current_score,
            "realized_return": self.realized_return,
            "realized_outcome_status": self.realized_outcome_status,
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "glyph": self.glyph,
            "named_check": self.named_check,
            "check_score": self.check_score,
            "replayability_class": self.replayability_class,
            "measurement_status": self.measurement_status,
            "source_module": self.source_module,
            "function_name": self.function_name,
            "replay_row_schema_version": self.replay_row_schema_version,
            "check_row_schema_version": self.check_row_schema_version,
            "single_date_replay_schema_version": self.single_date_replay_schema_version,
            "range_replay_schema_version": self.range_replay_schema_version,
            "audit_token": self.audit_token,
            "dataset_run_id": self.dataset_run_id,
        }


def _optional_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
