from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date

from market_health.calibration.authoritative_dataset import (
    AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION,
)
from market_health.calibration.check_inventory import REPLAYABILITY_CLASSES
from market_health.calibration.check_output import MEASUREMENT_STATUSES
from market_health.calibration.schema import ReplayArtifactRow

RESIDUAL_SCHEMA_VERSION = "calibration_forecast_residual.v1"
RESIDUAL_ATTRIBUTION_SCHEMA_VERSION = "calibration_residual_attribution.v1"

VALID_HORIZONS = ("H1", "H5")
RESIDUAL_HOT = "hot"
RESIDUAL_COLD = "cold"
RESIDUAL_NEUTRAL = "neutral"
RESIDUAL_DIRECTIONS = (RESIDUAL_HOT, RESIDUAL_COLD, RESIDUAL_NEUTRAL)

RESIDUAL_ATTRIBUTION_COLUMNS = (
    "schema_version",
    "replay_date",
    "symbol",
    "horizon",
    "target_date",
    "forecast_score",
    "realized_current_score",
    "residual",
    "residual_direction",
    "realized_return",
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
    "audit_token",
    "dataset_run_id",
    "authoritative_dataset_schema_version",
    "residual_attribution_run_id",
)


@dataclass(frozen=True)
class ResidualObservation:
    schema_version: str
    symbol: str
    origin_date: str
    target_date: str
    horizon: str
    forecast_score: float
    realized_current_score: float
    residual: float
    direction: str
    category: str | None = None
    slot: str | None = None
    glyph: str | None = None
    named_check: str | None = None

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResidualAttributionRow:
    replay_date: date
    symbol: str
    horizon: str
    target_date: date
    forecast_score: float
    realized_current_score: float
    residual: float
    residual_direction: str
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
    dataset_run_id: str
    realized_return: float | None = None
    authoritative_dataset_schema_version: str = (
        AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION
    )
    residual_attribution_run_id: str = "residual-attribution"
    schema_version: str = RESIDUAL_ATTRIBUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RESIDUAL_ATTRIBUTION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported residual attribution schema version: {self.schema_version}"
            )
        if (
            self.authoritative_dataset_schema_version
            != AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported authoritative dataset schema version for residual "
                f"attribution: {self.authoritative_dataset_schema_version}"
            )

        symbol = self.symbol.strip().upper()
        horizon = self.horizon.strip().upper()
        category = self.category.strip().upper()

        if not symbol:
            raise ValueError("residual attribution symbol is required")
        if horizon not in VALID_HORIZONS:
            raise ValueError(
                f"unsupported residual attribution horizon: {self.horizon}"
            )
        if category not in {"A", "B", "C", "D", "E"}:
            raise ValueError(
                f"unsupported residual attribution category: {self.category}"
            )
        if not 1 <= self.slot <= 6:
            raise ValueError(f"unsupported residual attribution slot: {self.slot}")
        if self.residual_direction not in RESIDUAL_DIRECTIONS:
            raise ValueError(
                f"unsupported residual attribution direction: {self.residual_direction}"
            )
        if self.residual_direction != residual_direction(self.residual):
            raise ValueError(
                "residual attribution direction does not match residual sign"
            )
        if round(self.residual, 8) != round(
            self.forecast_score - self.realized_current_score,
            8,
        ):
            raise ValueError(
                "residual attribution residual must equal forecast_score minus "
                "realized_current_score"
            )
        if self.replayability_class not in REPLAYABILITY_CLASSES:
            raise ValueError(
                f"unsupported residual replayability class: {self.replayability_class}"
            )
        if self.measurement_status not in MEASUREMENT_STATUSES:
            raise ValueError(
                f"unsupported residual measurement status: {self.measurement_status}"
            )

        for field_name in (
            "glyph",
            "named_check",
            "source_module",
            "function_name",
            "audit_token",
            "dataset_run_id",
            "residual_attribution_run_id",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"residual attribution {field_name} is required")

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "category", category)

    @property
    def category_slot(self) -> str:
        return f"{self.category}{self.slot}"

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_date": self.replay_date.isoformat(),
            "symbol": self.symbol,
            "horizon": self.horizon,
            "target_date": self.target_date.isoformat(),
            "forecast_score": self.forecast_score,
            "realized_current_score": self.realized_current_score,
            "residual": self.residual,
            "residual_direction": self.residual_direction,
            "realized_return": self.realized_return,
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
            "audit_token": self.audit_token,
            "dataset_run_id": self.dataset_run_id,
            "authoritative_dataset_schema_version": (
                self.authoritative_dataset_schema_version
            ),
            "residual_attribution_run_id": self.residual_attribution_run_id,
        }


@dataclass(frozen=True)
class ResidualSummary:
    schema_version: str
    group: dict[str, str | None]
    count: int
    mean_residual: float
    mean_abs_residual: float
    hot_count: int
    cold_count: int
    neutral_count: int

    def to_record(self) -> dict[str, object]:
        return asdict(self)


def residual_direction(residual: float) -> str:
    if residual > 0:
        return "hot"
    if residual < 0:
        return "cold"
    return "neutral"


def forecast_score_for_horizon(row: ReplayArtifactRow, horizon: str) -> float:
    horizon = horizon.upper()
    if horizon == "H1":
        return row.h1_score
    if horizon == "H5":
        return row.h5_score
    raise ValueError(f"unsupported residual horizon: {horizon}")


def build_residual_observation(
    *,
    forecast_row: ReplayArtifactRow,
    target_date: date,
    horizon: str,
    realized_current_score: float,
    category: str | None = None,
    slot: str | None = None,
    glyph: str | None = None,
    named_check: str | None = None,
) -> ResidualObservation:
    horizon = horizon.upper()
    forecast_score = forecast_score_for_horizon(forecast_row, horizon)
    residual = forecast_score - realized_current_score

    return ResidualObservation(
        schema_version=RESIDUAL_SCHEMA_VERSION,
        symbol=forecast_row.symbol,
        origin_date=forecast_row.replay_date.isoformat(),
        target_date=target_date.isoformat(),
        horizon=horizon,
        forecast_score=forecast_score,
        realized_current_score=realized_current_score,
        residual=residual,
        direction=residual_direction(residual),
        category=category,
        slot=slot,
        glyph=glyph,
        named_check=named_check,
    )


def summarize_residuals(
    observations: Iterable[ResidualObservation],
    *,
    group_by: Sequence[str] = ("horizon",),
) -> list[ResidualSummary]:
    buckets: dict[tuple[str | None, ...], list[ResidualObservation]] = defaultdict(list)

    for observation in observations:
        key = tuple(getattr(observation, field) for field in group_by)
        buckets[key].append(observation)

    summaries: list[ResidualSummary] = []
    for key, bucket in sorted(buckets.items(), key=lambda item: item[0]):
        residuals = [item.residual for item in bucket]
        count = len(residuals)
        group = dict(zip(group_by, key, strict=True))
        summaries.append(
            ResidualSummary(
                schema_version=RESIDUAL_SCHEMA_VERSION,
                group=group,
                count=count,
                mean_residual=sum(residuals) / count,
                mean_abs_residual=sum(abs(value) for value in residuals) / count,
                hot_count=sum(item.direction == "hot" for item in bucket),
                cold_count=sum(item.direction == "cold" for item in bucket),
                neutral_count=sum(item.direction == "neutral" for item in bucket),
            )
        )

    return summaries
