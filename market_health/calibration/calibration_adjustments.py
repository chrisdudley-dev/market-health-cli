from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from market_health.calibration.calibration_review import REVIEW_COLD, REVIEW_HOT
from market_health.calibration.residuals import VALID_HORIZONS

CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION = "calibration_adjustment_candidate.v1"

CALIBRATION_ADJUSTMENT_SCOPE_GLYPH = "glyph"
CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK = "named_check"
CALIBRATION_ADJUSTMENT_SCOPES = (
    CALIBRATION_ADJUSTMENT_SCOPE_GLYPH,
    CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK,
)

CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW = "glyph_review"
CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW = "named_check_review"
CALIBRATION_ADJUSTMENT_SOURCE_TABLES = (
    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW,
    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW,
)

CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE = "increase_score"
CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE = "decrease_score"
CALIBRATION_ADJUSTMENT_DIRECTIONS = (
    CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE,
    CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE,
)

CALIBRATION_ADJUSTMENT_CANDIDATE_REVIEW_CLASSIFICATIONS = (
    REVIEW_HOT,
    REVIEW_COLD,
)

CALIBRATION_ADJUSTMENT_CANDIDATE_COLUMNS = (
    "schema_version",
    "candidate_id",
    "candidate_scope",
    "source_review_table",
    "window_label",
    "window_start_date",
    "window_end_date",
    "horizon",
    "category",
    "slot",
    "category_slot",
    "glyph",
    "named_check",
    "review_classification",
    "adjustment_direction",
    "score_delta",
    "observation_count",
    "mean_residual",
    "mean_abs_residual",
    "residual_attribution_run_id",
    "calibration_review_run_id",
    "dry_run_only",
)


@dataclass(frozen=True)
class CalibrationAdjustmentCandidateRow:
    candidate_scope: str
    source_review_table: str
    horizon: str
    review_classification: str
    adjustment_direction: str
    score_delta: float
    observation_count: int
    mean_residual: float
    mean_abs_residual: float
    residual_attribution_run_id: str
    calibration_review_run_id: str
    category: str | None = None
    slot: int | None = None
    glyph: str | None = None
    named_check: str | None = None
    window_label: str = "full"
    window_start_date: date | None = None
    window_end_date: date | None = None
    dry_run_only: bool = True
    schema_version: str = CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration adjustment candidate schema version: "
                f"{self.schema_version}"
            )

        candidate_scope = _normalize_required_text(
            self.candidate_scope,
            "candidate_scope",
        )
        source_review_table = _normalize_required_text(
            self.source_review_table,
            "source_review_table",
        )
        horizon = _normalize_horizon(self.horizon)
        category = None if self.category is None else _normalize_category(self.category)
        glyph = (
            None
            if self.glyph is None
            else _normalize_required_text(
                self.glyph,
                "glyph",
            )
        )
        named_check = (
            None
            if self.named_check is None
            else _normalize_required_text(self.named_check, "named_check")
        )

        if candidate_scope not in CALIBRATION_ADJUSTMENT_SCOPES:
            raise ValueError(
                f"unsupported calibration adjustment candidate scope: {candidate_scope}"
            )
        if source_review_table not in CALIBRATION_ADJUSTMENT_SOURCE_TABLES:
            raise ValueError(
                "unsupported calibration adjustment source review table: "
                f"{source_review_table}"
            )
        _validate_scope_source_table(
            candidate_scope=candidate_scope,
            source_review_table=source_review_table,
        )
        if self.slot is not None:
            _validate_slot(self.slot)
        _validate_scope_context(
            candidate_scope=candidate_scope,
            category=category,
            slot=self.slot,
            glyph=glyph,
            named_check=named_check,
        )
        if self.review_classification not in (
            CALIBRATION_ADJUSTMENT_CANDIDATE_REVIEW_CLASSIFICATIONS
        ):
            raise ValueError(
                "unsupported calibration adjustment candidate review classification: "
                f"{self.review_classification}"
            )
        if self.adjustment_direction not in CALIBRATION_ADJUSTMENT_DIRECTIONS:
            raise ValueError(
                "unsupported calibration adjustment direction: "
                f"{self.adjustment_direction}"
            )
        _validate_adjustment_sign(
            review_classification=self.review_classification,
            adjustment_direction=self.adjustment_direction,
            score_delta=self.score_delta,
        )
        if self.observation_count <= 0:
            raise ValueError(
                "calibration adjustment candidate observation_count must be positive"
            )
        if not self.dry_run_only:
            raise ValueError(
                "calibration adjustment candidates must remain dry-run only"
            )

        _normalize_required_text(self.window_label, "window_label")
        _validate_window_bounds(self.window_start_date, self.window_end_date)
        _normalize_required_text(
            self.residual_attribution_run_id,
            "residual_attribution_run_id",
        )
        _normalize_required_text(
            self.calibration_review_run_id,
            "calibration_review_run_id",
        )

        object.__setattr__(self, "candidate_scope", candidate_scope)
        object.__setattr__(self, "source_review_table", source_review_table)
        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "glyph", glyph)
        object.__setattr__(self, "named_check", named_check)

    @property
    def category_slot(self) -> str | None:
        if self.category is None or self.slot is None:
            return None
        return f"{self.category}{self.slot}"

    @property
    def candidate_id(self) -> str:
        parts = (
            self.candidate_scope,
            self.source_review_table,
            self.window_label,
            _optional_date(self.window_start_date) or "all",
            _optional_date(self.window_end_date) or "all",
            self.horizon,
            self.category_slot or "any_slot",
            self.glyph or "any_glyph",
            self.named_check or "any_named_check",
            self.review_classification,
            self.adjustment_direction,
            f"{self.score_delta:.8f}",
            self.residual_attribution_run_id,
            self.calibration_review_run_id,
        )
        return "calibration-adjustment-candidate:" + ":".join(
            _candidate_id_part(part) for part in parts
        )

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "candidate_scope": self.candidate_scope,
            "source_review_table": self.source_review_table,
            "window_label": self.window_label,
            "window_start_date": _optional_date(self.window_start_date),
            "window_end_date": _optional_date(self.window_end_date),
            "horizon": self.horizon,
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "glyph": self.glyph,
            "named_check": self.named_check,
            "review_classification": self.review_classification,
            "adjustment_direction": self.adjustment_direction,
            "score_delta": self.score_delta,
            "observation_count": self.observation_count,
            "mean_residual": self.mean_residual,
            "mean_abs_residual": self.mean_abs_residual,
            "residual_attribution_run_id": self.residual_attribution_run_id,
            "calibration_review_run_id": self.calibration_review_run_id,
            "dry_run_only": self.dry_run_only,
        }


def _normalize_horizon(value: str) -> str:
    horizon = value.strip().upper()
    if horizon not in VALID_HORIZONS:
        raise ValueError(f"unsupported calibration adjustment horizon: {value}")
    return horizon


def _normalize_category(value: str) -> str:
    category = value.strip().upper()
    if category not in {"A", "B", "C", "D", "E"}:
        raise ValueError(f"unsupported calibration adjustment category: {value}")
    return category


def _validate_slot(value: int) -> None:
    if not 1 <= value <= 6:
        raise ValueError(f"unsupported calibration adjustment slot: {value}")


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"calibration adjustment {field_name} is required")
    return normalized


def _validate_scope_source_table(
    *,
    candidate_scope: str,
    source_review_table: str,
) -> None:
    expected_source_table = {
        CALIBRATION_ADJUSTMENT_SCOPE_GLYPH: (
            CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW
        ),
        CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK: (
            CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW
        ),
    }[candidate_scope]
    if source_review_table != expected_source_table:
        raise ValueError(
            "calibration adjustment candidate scope does not match source review table"
        )


def _validate_scope_context(
    *,
    candidate_scope: str,
    category: str | None,
    slot: int | None,
    glyph: str | None,
    named_check: str | None,
) -> None:
    if candidate_scope == CALIBRATION_ADJUSTMENT_SCOPE_GLYPH:
        if category is None or slot is None or glyph is None:
            raise ValueError(
                "glyph-scoped calibration adjustment candidates require category, "
                "slot, and glyph"
            )
        if named_check is not None:
            raise ValueError(
                "glyph-scoped calibration adjustment candidates cannot set named_check"
            )
        return

    if named_check is None:
        raise ValueError(
            "named-check-scoped calibration adjustment candidates require named_check"
        )
    if (category is None) != (slot is None):
        raise ValueError(
            "named-check-scoped calibration adjustment candidates require category "
            "and slot together"
        )


def _validate_adjustment_sign(
    *,
    review_classification: str,
    adjustment_direction: str,
    score_delta: float,
) -> None:
    if score_delta == 0:
        raise ValueError("calibration adjustment candidate score_delta cannot be zero")

    if review_classification == REVIEW_HOT:
        if adjustment_direction != CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE:
            raise ValueError("hot calibration candidates must decrease score")
        if score_delta >= 0:
            raise ValueError("hot calibration candidate score_delta must be negative")
        return

    if adjustment_direction != CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE:
        raise ValueError("cold calibration candidates must increase score")
    if score_delta <= 0:
        raise ValueError("cold calibration candidate score_delta must be positive")


def _validate_window_bounds(
    start_date: date | None,
    end_date: date | None,
) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("calibration adjustment window_start_date cannot be after end")


def _optional_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _candidate_id_part(value: str) -> str:
    return (
        value.strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )
