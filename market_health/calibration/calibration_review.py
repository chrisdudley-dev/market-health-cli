from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import median

from market_health.calibration.residuals import (
    RESIDUAL_COLD,
    RESIDUAL_HOT,
    RESIDUAL_NEUTRAL,
    VALID_HORIZONS,
    ResidualAttributionRow,
)

CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION = "calibration_glyph_review_row.v1"
CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION = (
    "calibration_named_check_review_row.v1"
)

REVIEW_HOT = RESIDUAL_HOT
REVIEW_COLD = RESIDUAL_COLD
REVIEW_INCONCLUSIVE = "inconclusive"
REVIEW_CLASSIFICATIONS = (REVIEW_HOT, REVIEW_COLD, REVIEW_INCONCLUSIVE)
DEFAULT_CALIBRATION_REVIEW_MIN_OBSERVATION_COUNT = 3

CALIBRATION_GLYPH_REVIEW_COLUMNS = (
    "schema_version",
    "window_label",
    "window_start_date",
    "window_end_date",
    "horizon",
    "category",
    "slot",
    "category_slot",
    "glyph",
    "observation_count",
    "min_observation_count",
    "mean_residual",
    "median_residual",
    "mean_abs_residual",
    "hot_count",
    "cold_count",
    "neutral_count",
    "review_classification",
    "residual_attribution_run_id",
)

CALIBRATION_NAMED_CHECK_REVIEW_COLUMNS = (
    "schema_version",
    "window_label",
    "window_start_date",
    "window_end_date",
    "horizon",
    "named_check",
    "category",
    "slot",
    "category_slot",
    "glyph",
    "observation_count",
    "min_observation_count",
    "mean_residual",
    "median_residual",
    "mean_abs_residual",
    "hot_count",
    "cold_count",
    "neutral_count",
    "review_classification",
    "residual_attribution_run_id",
)


@dataclass(frozen=True)
class CalibrationGlyphReviewRow:
    horizon: str
    category: str
    slot: int
    glyph: str
    observation_count: int
    min_observation_count: int
    mean_residual: float
    median_residual: float
    mean_abs_residual: float
    hot_count: int
    cold_count: int
    neutral_count: int
    review_classification: str
    residual_attribution_run_id: str
    window_label: str = "full"
    window_start_date: date | None = None
    window_end_date: date | None = None
    schema_version: str = CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_GLYPH_REVIEW_ROW_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration glyph review row schema version: "
                f"{self.schema_version}"
            )

        horizon = _normalize_horizon(self.horizon)
        category = _normalize_category(self.category)
        _validate_slot(self.slot)
        _validate_required_text(self.glyph, "glyph")
        _validate_review_counts(
            observation_count=self.observation_count,
            min_observation_count=self.min_observation_count,
            hot_count=self.hot_count,
            cold_count=self.cold_count,
            neutral_count=self.neutral_count,
            review_classification=self.review_classification,
        )
        _validate_required_text(
            self.residual_attribution_run_id,
            "residual_attribution_run_id",
        )
        _validate_required_text(self.window_label, "window_label")
        _validate_window_bounds(self.window_start_date, self.window_end_date)

        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "category", category)

    @property
    def category_slot(self) -> str:
        return f"{self.category}{self.slot}"

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "window_label": self.window_label,
            "window_start_date": _optional_date(self.window_start_date),
            "window_end_date": _optional_date(self.window_end_date),
            "horizon": self.horizon,
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "glyph": self.glyph,
            "observation_count": self.observation_count,
            "min_observation_count": self.min_observation_count,
            "mean_residual": self.mean_residual,
            "median_residual": self.median_residual,
            "mean_abs_residual": self.mean_abs_residual,
            "hot_count": self.hot_count,
            "cold_count": self.cold_count,
            "neutral_count": self.neutral_count,
            "review_classification": self.review_classification,
            "residual_attribution_run_id": self.residual_attribution_run_id,
        }


@dataclass(frozen=True)
class CalibrationNamedCheckReviewRow:
    horizon: str
    named_check: str
    observation_count: int
    min_observation_count: int
    mean_residual: float
    median_residual: float
    mean_abs_residual: float
    hot_count: int
    cold_count: int
    neutral_count: int
    review_classification: str
    residual_attribution_run_id: str
    category: str | None = None
    slot: int | None = None
    category_slot: str | None = None
    glyph: str | None = None
    window_label: str = "full"
    window_start_date: date | None = None
    window_end_date: date | None = None
    schema_version: str = CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_NAMED_CHECK_REVIEW_ROW_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration named-check review row schema version: "
                f"{self.schema_version}"
            )

        horizon = _normalize_horizon(self.horizon)
        category = None if self.category is None else _normalize_category(self.category)
        if self.slot is not None:
            _validate_slot(self.slot)
        inferred_category_slot = _infer_category_slot(
            category=category,
            slot=self.slot,
            category_slot=self.category_slot,
        )

        _validate_required_text(self.named_check, "named_check")
        if self.glyph is not None:
            _validate_required_text(self.glyph, "glyph")
        _validate_review_counts(
            observation_count=self.observation_count,
            min_observation_count=self.min_observation_count,
            hot_count=self.hot_count,
            cold_count=self.cold_count,
            neutral_count=self.neutral_count,
            review_classification=self.review_classification,
        )
        _validate_required_text(
            self.residual_attribution_run_id,
            "residual_attribution_run_id",
        )
        _validate_required_text(self.window_label, "window_label")
        _validate_window_bounds(self.window_start_date, self.window_end_date)

        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "category_slot", inferred_category_slot)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "window_label": self.window_label,
            "window_start_date": _optional_date(self.window_start_date),
            "window_end_date": _optional_date(self.window_end_date),
            "horizon": self.horizon,
            "named_check": self.named_check,
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "glyph": self.glyph,
            "observation_count": self.observation_count,
            "min_observation_count": self.min_observation_count,
            "mean_residual": self.mean_residual,
            "median_residual": self.median_residual,
            "mean_abs_residual": self.mean_abs_residual,
            "hot_count": self.hot_count,
            "cold_count": self.cold_count,
            "neutral_count": self.neutral_count,
            "review_classification": self.review_classification,
            "residual_attribution_run_id": self.residual_attribution_run_id,
        }


def build_glyph_calibration_review_rows(
    rows: Iterable[ResidualAttributionRow],
    *,
    min_observation_count: int = DEFAULT_CALIBRATION_REVIEW_MIN_OBSERVATION_COUNT,
    window_label: str = "full",
    window_start_date: date | None = None,
    window_end_date: date | None = None,
) -> tuple[CalibrationGlyphReviewRow, ...]:
    buckets: dict[tuple[str, str, int, str], list[ResidualAttributionRow]] = (
        defaultdict(list)
    )

    for row in rows:
        buckets[(row.horizon, row.category, row.slot, row.glyph)].append(row)

    return tuple(
        _build_glyph_review_row(
            key,
            bucket,
            min_observation_count=min_observation_count,
            window_label=window_label,
            window_start_date=window_start_date,
            window_end_date=window_end_date,
        )
        for key, bucket in sorted(buckets.items(), key=lambda item: item[0])
    )


def calibration_review_classification(
    *,
    observation_count: int,
    min_observation_count: int,
    mean_residual: float,
) -> str:
    if observation_count < min_observation_count:
        return REVIEW_INCONCLUSIVE
    if mean_residual > 0:
        return REVIEW_HOT
    if mean_residual < 0:
        return REVIEW_COLD
    return REVIEW_INCONCLUSIVE


def _build_glyph_review_row(
    key: tuple[str, str, int, str],
    bucket: Sequence[ResidualAttributionRow],
    *,
    min_observation_count: int,
    window_label: str,
    window_start_date: date | None,
    window_end_date: date | None,
) -> CalibrationGlyphReviewRow:
    horizon, category, slot, glyph = key
    residuals = [row.residual for row in bucket]
    count = len(residuals)
    mean_residual = round(sum(residuals) / count, 8)

    return CalibrationGlyphReviewRow(
        horizon=horizon,
        category=category,
        slot=slot,
        glyph=glyph,
        observation_count=count,
        min_observation_count=min_observation_count,
        mean_residual=mean_residual,
        median_residual=round(float(median(residuals)), 8),
        mean_abs_residual=round(sum(abs(value) for value in residuals) / count, 8),
        hot_count=sum(row.residual_direction == RESIDUAL_HOT for row in bucket),
        cold_count=sum(row.residual_direction == RESIDUAL_COLD for row in bucket),
        neutral_count=sum(row.residual_direction == RESIDUAL_NEUTRAL for row in bucket),
        review_classification=calibration_review_classification(
            observation_count=count,
            min_observation_count=min_observation_count,
            mean_residual=mean_residual,
        ),
        residual_attribution_run_id=_single_residual_attribution_run_id(bucket),
        window_label=window_label,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
    )


def _single_residual_attribution_run_id(
    rows: Sequence[ResidualAttributionRow],
) -> str:
    run_ids = sorted({row.residual_attribution_run_id for row in rows})
    if len(run_ids) != 1:
        raise ValueError(
            "calibration review glyph rows require exactly one "
            "residual_attribution_run_id per group"
        )
    return run_ids[0]


def _normalize_horizon(value: str) -> str:
    horizon = value.strip().upper()
    if horizon not in VALID_HORIZONS:
        raise ValueError(f"unsupported calibration review horizon: {value}")
    return horizon


def _normalize_category(value: str) -> str:
    category = value.strip().upper()
    if category not in {"A", "B", "C", "D", "E"}:
        raise ValueError(f"unsupported calibration review category: {value}")
    return category


def _validate_slot(value: int) -> None:
    if not 1 <= value <= 6:
        raise ValueError(f"unsupported calibration review slot: {value}")


def _validate_required_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"calibration review {field_name} is required")


def _validate_review_counts(
    *,
    observation_count: int,
    min_observation_count: int,
    hot_count: int,
    cold_count: int,
    neutral_count: int,
    review_classification: str,
) -> None:
    if observation_count <= 0:
        raise ValueError("calibration review observation_count must be positive")
    if min_observation_count <= 0:
        raise ValueError("calibration review min_observation_count must be positive")
    if hot_count < 0 or cold_count < 0 or neutral_count < 0:
        raise ValueError("calibration review direction counts cannot be negative")
    if hot_count + cold_count + neutral_count != observation_count:
        raise ValueError(
            "calibration review direction counts must equal observation_count"
        )
    if review_classification not in REVIEW_CLASSIFICATIONS:
        raise ValueError(
            f"unsupported calibration review classification: {review_classification}"
        )
    if (
        observation_count < min_observation_count
        and review_classification != REVIEW_INCONCLUSIVE
    ):
        raise ValueError(
            "calibration review rows below min_observation_count must be inconclusive"
        )


def _infer_category_slot(
    *,
    category: str | None,
    slot: int | None,
    category_slot: str | None,
) -> str | None:
    if category_slot is not None and not category_slot.strip():
        raise ValueError("calibration review category_slot cannot be blank")

    inferred = None
    if category is not None and slot is not None:
        inferred = f"{category}{slot}"

    if category_slot is None:
        return inferred

    normalized = category_slot.strip().upper()
    if inferred is not None and normalized != inferred:
        raise ValueError(
            "calibration review category_slot must match category and slot"
        )
    return normalized


def _validate_window_bounds(
    window_start_date: date | None,
    window_end_date: date | None,
) -> None:
    if (
        window_start_date is not None
        and window_end_date is not None
        and window_start_date > window_end_date
    ):
        raise ValueError(
            "calibration review window_start_date must be <= window_end_date"
        )


def _optional_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
