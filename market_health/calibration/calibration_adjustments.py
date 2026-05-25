from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from market_health.calibration.calibration_review import (
    REVIEW_COLD,
    REVIEW_HOT,
    CalibrationGlyphReviewRow,
    CalibrationNamedCheckReviewRow,
)
from market_health.calibration.residuals import (
    VALID_HORIZONS,
    ResidualAttributionRow,
    residual_direction,
)

CALIBRATION_ADJUSTMENT_CANDIDATE_SCHEMA_VERSION = "calibration_adjustment_candidate.v1"
CALIBRATION_DRY_RUN_SIMULATION_SCHEMA_VERSION = "calibration_dry_run_simulation.v1"

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

DEFAULT_CALIBRATION_ADJUSTMENT_MIN_OBSERVATION_COUNT = 3

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


CALIBRATION_DRY_RUN_SIMULATION_COLUMNS = (
    "schema_version",
    "replay_date",
    "symbol",
    "horizon",
    "target_date",
    "category",
    "slot",
    "category_slot",
    "glyph",
    "named_check",
    "baseline_forecast_score",
    "simulated_forecast_score",
    "realized_current_score",
    "baseline_residual",
    "simulated_residual",
    "baseline_residual_direction",
    "simulated_residual_direction",
    "applied_score_delta",
    "applied_candidate_count",
    "applied_candidate_ids",
    "residual_attribution_run_id",
    "calibration_review_run_id",
    "dry_run_simulation_run_id",
    "source_residual_schema_version",
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


@dataclass(frozen=True)
class CalibrationDryRunSimulationRow:
    replay_date: date
    symbol: str
    horizon: str
    target_date: date
    category: str
    slot: int
    glyph: str
    named_check: str
    baseline_forecast_score: float
    simulated_forecast_score: float
    realized_current_score: float
    baseline_residual: float
    simulated_residual: float
    baseline_residual_direction: str
    simulated_residual_direction: str
    applied_score_delta: float
    applied_candidate_ids: tuple[str, ...]
    residual_attribution_run_id: str
    calibration_review_run_id: str
    dry_run_simulation_run_id: str
    source_residual_schema_version: str
    dry_run_only: bool = True
    schema_version: str = CALIBRATION_DRY_RUN_SIMULATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_DRY_RUN_SIMULATION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported calibration dry-run simulation schema version: "
                f"{self.schema_version}"
            )

        symbol = _normalize_required_text(self.symbol, "symbol").upper()
        horizon = _normalize_horizon(self.horizon)
        category = _normalize_category(self.category)
        _validate_slot(self.slot)
        _normalize_required_text(self.glyph, "glyph")
        _normalize_required_text(self.named_check, "named_check")
        _normalize_required_text(
            self.residual_attribution_run_id,
            "residual_attribution_run_id",
        )
        _normalize_required_text(
            self.calibration_review_run_id,
            "calibration_review_run_id",
        )
        _normalize_required_text(
            self.dry_run_simulation_run_id,
            "dry_run_simulation_run_id",
        )
        _normalize_required_text(
            self.source_residual_schema_version,
            "source_residual_schema_version",
        )

        if not self.dry_run_only:
            raise ValueError("calibration dry-run simulation rows must be dry-run only")
        if not self.applied_candidate_ids:
            raise ValueError(
                "calibration dry-run simulation rows require applied_candidate_ids"
            )
        if len(set(self.applied_candidate_ids)) != len(self.applied_candidate_ids):
            raise ValueError(
                "calibration dry-run simulation applied_candidate_ids must be unique"
            )
        if tuple(sorted(self.applied_candidate_ids)) != self.applied_candidate_ids:
            raise ValueError(
                "calibration dry-run simulation applied_candidate_ids must be sorted"
            )
        if round(
            self.baseline_residual,
            8,
        ) != round(self.baseline_forecast_score - self.realized_current_score, 8):
            raise ValueError(
                "baseline_residual must equal baseline_forecast_score minus "
                "realized_current_score"
            )
        if round(
            self.simulated_residual,
            8,
        ) != round(self.simulated_forecast_score - self.realized_current_score, 8):
            raise ValueError(
                "simulated_residual must equal simulated_forecast_score minus "
                "realized_current_score"
            )
        if self.baseline_residual_direction != residual_direction(
            self.baseline_residual
        ):
            raise ValueError(
                "baseline_residual_direction does not match baseline residual sign"
            )
        if self.simulated_residual_direction != residual_direction(
            self.simulated_residual
        ):
            raise ValueError(
                "simulated_residual_direction does not match simulated residual sign"
            )
        if round(
            self.applied_score_delta,
            8,
        ) != round(self.simulated_forecast_score - self.baseline_forecast_score, 8):
            raise ValueError(
                "applied_score_delta must equal simulated forecast minus baseline "
                "forecast"
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "category", category)

    @property
    def category_slot(self) -> str:
        return f"{self.category}{self.slot}"

    @property
    def applied_candidate_count(self) -> int:
        return len(self.applied_candidate_ids)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "symbol": self.symbol,
            "horizon": self.horizon,
            "target_date": self.target_date.isoformat(),
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "glyph": self.glyph,
            "named_check": self.named_check,
            "baseline_forecast_score": self.baseline_forecast_score,
            "simulated_forecast_score": self.simulated_forecast_score,
            "realized_current_score": self.realized_current_score,
            "baseline_residual": self.baseline_residual,
            "simulated_residual": self.simulated_residual,
            "baseline_residual_direction": self.baseline_residual_direction,
            "simulated_residual_direction": self.simulated_residual_direction,
            "applied_score_delta": self.applied_score_delta,
            "applied_candidate_count": self.applied_candidate_count,
            "applied_candidate_ids": "|".join(self.applied_candidate_ids),
            "residual_attribution_run_id": self.residual_attribution_run_id,
            "calibration_review_run_id": self.calibration_review_run_id,
            "dry_run_simulation_run_id": self.dry_run_simulation_run_id,
            "source_residual_schema_version": self.source_residual_schema_version,
            "dry_run_only": self.dry_run_only,
        }


def apply_calibration_adjustment_candidates_dry_run(
    rows: Iterable[ResidualAttributionRow],
    candidates: Iterable[CalibrationAdjustmentCandidateRow],
    *,
    dry_run_simulation_run_id: str = "calibration-dry-run",
) -> tuple[CalibrationDryRunSimulationRow, ...]:
    _normalize_required_text(
        dry_run_simulation_run_id,
        "dry_run_simulation_run_id",
    )
    source_rows = tuple(rows)
    candidate_rows = tuple(sorted(candidates, key=_candidate_sort_key))

    _validate_candidate_set_for_simulation(candidate_rows)

    simulation_rows: list[CalibrationDryRunSimulationRow] = []
    for row in sorted(source_rows, key=_residual_row_sort_key):
        matched_candidates = tuple(
            candidate
            for candidate in candidate_rows
            if _candidate_matches_residual_row(candidate, row)
        )
        if not matched_candidates:
            continue

        applied_score_delta = round(
            sum(candidate.score_delta for candidate in matched_candidates),
            8,
        )
        simulated_forecast_score = _clamp_score(
            round(row.forecast_score + applied_score_delta, 8)
        )
        applied_score_delta = round(simulated_forecast_score - row.forecast_score, 8)
        simulated_residual = round(
            simulated_forecast_score - row.realized_current_score,
            8,
        )

        simulation_rows.append(
            CalibrationDryRunSimulationRow(
                replay_date=row.replay_date,
                symbol=row.symbol,
                horizon=row.horizon,
                target_date=row.target_date,
                category=row.category,
                slot=row.slot,
                glyph=row.glyph,
                named_check=row.named_check,
                baseline_forecast_score=row.forecast_score,
                simulated_forecast_score=simulated_forecast_score,
                realized_current_score=row.realized_current_score,
                baseline_residual=row.residual,
                simulated_residual=simulated_residual,
                baseline_residual_direction=row.residual_direction,
                simulated_residual_direction=residual_direction(simulated_residual),
                applied_score_delta=applied_score_delta,
                applied_candidate_ids=tuple(
                    candidate.candidate_id for candidate in matched_candidates
                ),
                residual_attribution_run_id=row.residual_attribution_run_id,
                calibration_review_run_id=_single_calibration_review_run_id(
                    matched_candidates
                ),
                dry_run_simulation_run_id=dry_run_simulation_run_id,
                source_residual_schema_version=row.schema_version,
            )
        )

    return tuple(simulation_rows)


def _validate_candidate_set_for_simulation(
    candidates: tuple[CalibrationAdjustmentCandidateRow, ...],
) -> None:
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("calibration dry-run candidate IDs must be unique")
    for candidate in candidates:
        if not candidate.dry_run_only:
            raise ValueError("calibration dry-run candidates must be dry-run only")


def _candidate_matches_residual_row(
    candidate: CalibrationAdjustmentCandidateRow,
    row: ResidualAttributionRow,
) -> bool:
    if candidate.horizon != row.horizon:
        return False

    if candidate.candidate_scope == CALIBRATION_ADJUSTMENT_SCOPE_GLYPH:
        return (
            candidate.category == row.category
            and candidate.slot == row.slot
            and candidate.glyph == row.glyph
        )

    if candidate.named_check != row.named_check:
        return False
    if candidate.category is not None and candidate.category != row.category:
        return False
    if candidate.slot is not None and candidate.slot != row.slot:
        return False
    if candidate.glyph is not None and candidate.glyph != row.glyph:
        return False
    return True


def _single_calibration_review_run_id(
    candidates: tuple[CalibrationAdjustmentCandidateRow, ...],
) -> str:
    run_ids = sorted({candidate.calibration_review_run_id for candidate in candidates})
    if len(run_ids) != 1:
        raise ValueError(
            "matched calibration dry-run candidates must share one "
            "calibration_review_run_id"
        )
    return run_ids[0]


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 8)


def _residual_row_sort_key(row: ResidualAttributionRow) -> tuple[object, ...]:
    return (
        row.replay_date.isoformat(),
        row.symbol,
        row.horizon,
        row.category,
        row.slot,
        row.glyph,
        row.named_check,
    )


def build_calibration_adjustment_candidates_from_review_tables(
    *,
    glyph_review_rows: Iterable[CalibrationGlyphReviewRow] = (),
    named_check_review_rows: Iterable[CalibrationNamedCheckReviewRow] = (),
    calibration_review_run_id: str = "calibration-review",
    min_observation_count: int = DEFAULT_CALIBRATION_ADJUSTMENT_MIN_OBSERVATION_COUNT,
) -> tuple[CalibrationAdjustmentCandidateRow, ...]:
    return tuple(
        sorted(
            (
                *build_glyph_calibration_adjustment_candidates(
                    glyph_review_rows,
                    calibration_review_run_id=calibration_review_run_id,
                    min_observation_count=min_observation_count,
                ),
                *build_named_check_calibration_adjustment_candidates(
                    named_check_review_rows,
                    calibration_review_run_id=calibration_review_run_id,
                    min_observation_count=min_observation_count,
                ),
            ),
            key=_candidate_sort_key,
        )
    )


def build_glyph_calibration_adjustment_candidates(
    rows: Iterable[CalibrationGlyphReviewRow],
    *,
    calibration_review_run_id: str = "calibration-review",
    min_observation_count: int = DEFAULT_CALIBRATION_ADJUSTMENT_MIN_OBSERVATION_COUNT,
) -> tuple[CalibrationAdjustmentCandidateRow, ...]:
    _validate_candidate_builder_inputs(
        calibration_review_run_id=calibration_review_run_id,
        min_observation_count=min_observation_count,
    )

    candidates: list[CalibrationAdjustmentCandidateRow] = []
    for row in sorted(rows, key=_glyph_review_row_sort_key):
        if not _review_row_is_candidate_eligible(row, min_observation_count):
            continue

        candidates.append(
            CalibrationAdjustmentCandidateRow(
                candidate_scope=CALIBRATION_ADJUSTMENT_SCOPE_GLYPH,
                source_review_table=CALIBRATION_ADJUSTMENT_SOURCE_TABLE_GLYPH_REVIEW,
                horizon=row.horizon,
                category=row.category,
                slot=row.slot,
                glyph=row.glyph,
                review_classification=row.review_classification,
                adjustment_direction=_adjustment_direction_for_review_classification(
                    row.review_classification
                ),
                score_delta=_score_delta_for_mean_residual(row.mean_residual),
                observation_count=row.observation_count,
                mean_residual=row.mean_residual,
                mean_abs_residual=row.mean_abs_residual,
                residual_attribution_run_id=row.residual_attribution_run_id,
                calibration_review_run_id=calibration_review_run_id,
                window_label=row.window_label,
                window_start_date=row.window_start_date,
                window_end_date=row.window_end_date,
            )
        )

    return tuple(candidates)


def build_named_check_calibration_adjustment_candidates(
    rows: Iterable[CalibrationNamedCheckReviewRow],
    *,
    calibration_review_run_id: str = "calibration-review",
    min_observation_count: int = DEFAULT_CALIBRATION_ADJUSTMENT_MIN_OBSERVATION_COUNT,
) -> tuple[CalibrationAdjustmentCandidateRow, ...]:
    _validate_candidate_builder_inputs(
        calibration_review_run_id=calibration_review_run_id,
        min_observation_count=min_observation_count,
    )

    candidates: list[CalibrationAdjustmentCandidateRow] = []
    for row in sorted(rows, key=_named_check_review_row_sort_key):
        if not _review_row_is_candidate_eligible(row, min_observation_count):
            continue

        candidates.append(
            CalibrationAdjustmentCandidateRow(
                candidate_scope=CALIBRATION_ADJUSTMENT_SCOPE_NAMED_CHECK,
                source_review_table=(
                    CALIBRATION_ADJUSTMENT_SOURCE_TABLE_NAMED_CHECK_REVIEW
                ),
                horizon=row.horizon,
                category=row.category,
                slot=row.slot,
                glyph=row.glyph,
                named_check=row.named_check,
                review_classification=row.review_classification,
                adjustment_direction=_adjustment_direction_for_review_classification(
                    row.review_classification
                ),
                score_delta=_score_delta_for_mean_residual(row.mean_residual),
                observation_count=row.observation_count,
                mean_residual=row.mean_residual,
                mean_abs_residual=row.mean_abs_residual,
                residual_attribution_run_id=row.residual_attribution_run_id,
                calibration_review_run_id=calibration_review_run_id,
                window_label=row.window_label,
                window_start_date=row.window_start_date,
                window_end_date=row.window_end_date,
            )
        )

    return tuple(candidates)


def _validate_candidate_builder_inputs(
    *,
    calibration_review_run_id: str,
    min_observation_count: int,
) -> None:
    _normalize_required_text(calibration_review_run_id, "calibration_review_run_id")
    if min_observation_count <= 0:
        raise ValueError("min_observation_count must be positive")


def _review_row_is_candidate_eligible(
    row: CalibrationGlyphReviewRow | CalibrationNamedCheckReviewRow,
    min_observation_count: int,
) -> bool:
    if row.review_classification not in (
        CALIBRATION_ADJUSTMENT_CANDIDATE_REVIEW_CLASSIFICATIONS
    ):
        return False
    if row.observation_count < min_observation_count:
        return False
    if row.observation_count < row.min_observation_count:
        return False
    return row.mean_residual != 0


def _adjustment_direction_for_review_classification(
    review_classification: str,
) -> str:
    if review_classification == REVIEW_HOT:
        return CALIBRATION_ADJUSTMENT_DIRECTION_DECREASE_SCORE
    if review_classification == REVIEW_COLD:
        return CALIBRATION_ADJUSTMENT_DIRECTION_INCREASE_SCORE
    raise ValueError(
        "unsupported calibration adjustment candidate review classification: "
        f"{review_classification}"
    )


def _score_delta_for_mean_residual(mean_residual: float) -> float:
    return round(-mean_residual, 8)


def _candidate_sort_key(row: CalibrationAdjustmentCandidateRow) -> str:
    return row.candidate_id


def _glyph_review_row_sort_key(row: CalibrationGlyphReviewRow) -> tuple[object, ...]:
    return (
        row.window_label,
        _optional_date(row.window_start_date) or "",
        _optional_date(row.window_end_date) or "",
        row.horizon,
        row.category,
        row.slot,
        row.glyph,
    )


def _named_check_review_row_sort_key(
    row: CalibrationNamedCheckReviewRow,
) -> tuple[object, ...]:
    return (
        row.window_label,
        _optional_date(row.window_start_date) or "",
        _optional_date(row.window_end_date) or "",
        row.horizon,
        row.named_check,
        row.category or "",
        row.slot or 0,
        row.glyph or "",
    )


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
