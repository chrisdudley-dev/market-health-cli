from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from market_health.calibration.check_inventory import (
    CheckInventoryRow,
    REPLAYABILITY_CLASSES,
    REPLAYABILITY_EVENT_DEPENDENT,
    REPLAYABILITY_EXCLUDED,
    REPLAYABILITY_NEUTRAL_FALLBACK,
    iter_check_inventory,
)

CHECK_REPLAY_ROW_SCHEMA_VERSION = "calibration_check_replay_row.v1"

VALID_HORIZONS = ("C", "H1", "H5")
MEASUREMENT_MEASURED = "measured"
MEASUREMENT_FALLBACK_NEUTRAL = "fallback_neutral"
MEASUREMENT_EVENT_UNAVAILABLE = "event_unavailable"
MEASUREMENT_EXCLUDED = "excluded"

MEASUREMENT_STATUSES = (
    MEASUREMENT_MEASURED,
    MEASUREMENT_FALLBACK_NEUTRAL,
    MEASUREMENT_EVENT_UNAVAILABLE,
    MEASUREMENT_EXCLUDED,
)

CHECK_REPLAY_ROW_COLUMNS = (
    "schema_version",
    "replay_date",
    "symbol",
    "category",
    "slot",
    "category_slot",
    "horizon",
    "glyph",
    "named_check",
    "score",
    "replayability_class",
    "measurement_status",
    "source_module",
    "function_name",
)


REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION = (
    "reviewed_check_score_calibration_adjustment.v1"
)


@dataclass(frozen=True)
class ReviewedCheckScoreCalibrationAdjustment:
    horizon: str
    category: str
    slot: int
    score_delta: float
    calibration_review_run_id: str
    dry_run_simulation_run_id: str
    approved_by: str
    rationale: str
    schema_version: str = REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        horizon = self.horizon.strip().upper()
        category = self.category.strip().upper()

        if (
            self.schema_version
            != REVIEWED_CHECK_SCORE_CALIBRATION_ADJUSTMENT_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported reviewed check score calibration adjustment schema "
                f"version: {self.schema_version}"
            )
        if horizon not in VALID_HORIZONS:
            raise ValueError(
                f"unsupported reviewed check score calibration horizon: {self.horizon}"
            )
        if category not in {"A", "B", "C", "D", "E"}:
            raise ValueError(
                f"unsupported reviewed check score calibration category: {self.category}"
            )
        if not 1 <= self.slot <= 6:
            raise ValueError(
                f"unsupported reviewed check score calibration slot: {self.slot}"
            )
        if self.score_delta == 0:
            raise ValueError(
                "reviewed check score calibration score_delta cannot be zero"
            )
        for field_name in (
            "calibration_review_run_id",
            "dry_run_simulation_run_id",
            "approved_by",
            "rationale",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(
                    f"reviewed check score calibration {field_name} is required"
                )

        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "category", category)

    @property
    def category_slot(self) -> str:
        return f"{self.category}{self.slot}"

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "horizon": self.horizon,
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "score_delta": self.score_delta,
            "calibration_review_run_id": self.calibration_review_run_id,
            "dry_run_simulation_run_id": self.dry_run_simulation_run_id,
            "approved_by": self.approved_by,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class CheckReplayRow:
    replay_date: date
    symbol: str
    category: str
    slot: int
    horizon: str
    glyph: str
    named_check: str
    score: float
    replayability_class: str
    measurement_status: str
    source_module: str
    function_name: str
    schema_version: str = CHECK_REPLAY_ROW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        category = self.category.strip().upper()
        symbol = self.symbol.strip().upper()
        horizon = self.horizon.strip().upper()

        if category not in {"A", "B", "C", "D", "E"}:
            raise ValueError(f"unsupported check category: {self.category}")
        if not 1 <= self.slot <= 6:
            raise ValueError(f"unsupported check slot: {self.slot}")
        if not symbol:
            raise ValueError("check replay row symbol is required")
        if horizon not in VALID_HORIZONS:
            raise ValueError(f"unsupported check horizon: {self.horizon}")
        if self.replayability_class not in REPLAYABILITY_CLASSES:
            raise ValueError(
                f"unsupported replayability class: {self.replayability_class}"
            )
        if self.measurement_status not in MEASUREMENT_STATUSES:
            raise ValueError(
                f"unsupported measurement status: {self.measurement_status}"
            )
        if self.schema_version != CHECK_REPLAY_ROW_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported check replay row schema version: {self.schema_version}"
            )

        object.__setattr__(self, "category", category)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "horizon", horizon)

    @property
    def category_slot(self) -> str:
        return f"{self.category}{self.slot}"

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "symbol": self.symbol,
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "horizon": self.horizon,
            "glyph": self.glyph,
            "named_check": self.named_check,
            "score": self.score,
            "replayability_class": self.replayability_class,
            "measurement_status": self.measurement_status,
            "source_module": self.source_module,
            "function_name": self.function_name,
        }


def build_fixture_check_replay_rows(
    *,
    replay_date: date,
    symbols: Iterable[str],
    horizons: Iterable[str] = VALID_HORIZONS,
    inventory: Iterable[CheckInventoryRow] | None = None,
    reviewed_calibration_adjustments: Iterable[
        ReviewedCheckScoreCalibrationAdjustment
    ] = (),
) -> tuple[CheckReplayRow, ...]:
    selected_inventory = (
        iter_check_inventory() if inventory is None else tuple(inventory)
    )
    normalized_symbols = _normalize_symbols(symbols)
    normalized_horizons = _normalize_horizons(horizons)

    rows: list[CheckReplayRow] = []
    for symbol in normalized_symbols:
        for item in selected_inventory:
            for horizon in normalized_horizons:
                rows.append(
                    CheckReplayRow(
                        replay_date=replay_date,
                        symbol=symbol,
                        category=item.category,
                        slot=item.slot,
                        horizon=horizon,
                        glyph=_fixture_glyph(item.slot, horizon),
                        named_check=item.named_check,
                        score=_fixture_score(item, horizon),
                        replayability_class=item.replayability_class,
                        measurement_status=_measurement_status_for_inventory(item),
                        source_module=item.source_module,
                        function_name=item.function_name,
                    )
                )

    calibrated_rows = apply_reviewed_check_score_calibration_adjustments(
        rows,
        reviewed_calibration_adjustments,
    )

    return tuple(
        sorted(
            calibrated_rows,
            key=lambda row: (row.symbol, row.category, row.slot, row.horizon),
        )
    )


def apply_reviewed_check_score_calibration_adjustments(
    rows: Iterable[CheckReplayRow],
    adjustments: Iterable[ReviewedCheckScoreCalibrationAdjustment],
) -> tuple[CheckReplayRow, ...]:
    source_rows = tuple(rows)
    adjustment_rows = tuple(adjustments)
    if not adjustment_rows:
        return source_rows

    _validate_reviewed_calibration_adjustments(adjustment_rows)

    adjusted_rows: list[CheckReplayRow] = []
    for row in source_rows:
        score_delta = round(
            sum(
                adjustment.score_delta
                for adjustment in adjustment_rows
                if _reviewed_adjustment_matches_check_row(adjustment, row)
            ),
            8,
        )
        if score_delta == 0:
            adjusted_rows.append(row)
            continue

        adjusted_rows.append(
            CheckReplayRow(
                replay_date=row.replay_date,
                symbol=row.symbol,
                category=row.category,
                slot=row.slot,
                horizon=row.horizon,
                glyph=row.glyph,
                named_check=row.named_check,
                score=_clamp_check_score(row.score + score_delta),
                replayability_class=row.replayability_class,
                measurement_status=row.measurement_status,
                source_module=row.source_module,
                function_name=row.function_name,
                schema_version=row.schema_version,
            )
        )

    return tuple(adjusted_rows)


def _validate_reviewed_calibration_adjustments(
    adjustments: tuple[ReviewedCheckScoreCalibrationAdjustment, ...],
) -> None:
    scopes = [
        (adjustment.horizon, adjustment.category, adjustment.slot)
        for adjustment in adjustments
    ]
    if len(set(scopes)) != len(scopes):
        raise ValueError(
            "reviewed check score calibration adjustments must have unique "
            "horizon/category/slot scopes"
        )


def _reviewed_adjustment_matches_check_row(
    adjustment: ReviewedCheckScoreCalibrationAdjustment,
    row: CheckReplayRow,
) -> bool:
    return (
        adjustment.horizon == row.horizon
        and adjustment.category == row.category
        and adjustment.slot == row.slot
    )


def _clamp_check_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 4)


def _measurement_status_for_inventory(item: CheckInventoryRow) -> str:
    if item.replayability_class == REPLAYABILITY_EVENT_DEPENDENT:
        return MEASUREMENT_EVENT_UNAVAILABLE
    if item.replayability_class == REPLAYABILITY_NEUTRAL_FALLBACK:
        return MEASUREMENT_FALLBACK_NEUTRAL
    if item.replayability_class == REPLAYABILITY_EXCLUDED:
        return MEASUREMENT_EXCLUDED
    return MEASUREMENT_MEASURED


def _fixture_score(item: CheckInventoryRow, horizon: str) -> float:
    horizon_offset = {"C": 0.0, "H1": 0.1, "H5": 0.2}[horizon]
    return round(float(item.slot) + horizon_offset, 4)


def _fixture_glyph(slot: int, horizon: str) -> str:
    prefix = {"C": "c", "H1": "h", "H5": "f"}[horizon]
    return f"{prefix}{slot}"


def _normalize_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = symbol.strip().upper()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return tuple(normalized)


def _normalize_horizons(horizons: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for horizon in horizons:
        value = horizon.strip().upper()
        if value not in VALID_HORIZONS:
            raise ValueError(f"unsupported check horizon: {horizon}")
        if value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return tuple(normalized)
