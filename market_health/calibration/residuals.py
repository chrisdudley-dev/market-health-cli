from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date

from market_health.calibration.authoritative_dataset import (
    AUTHORITATIVE_REPLAY_DATASET_SCHEMA_VERSION,
    REALIZED_OUTCOME_AVAILABLE,
    AuthoritativeReplayDatasetRow,
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

RESIDUAL_ATTRIBUTION_SUMMARY_SCHEMA_VERSION = (
    "calibration_residual_attribution_summary.v1"
)

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

RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS = (
    "schema_version",
    "group_name",
    "group_value",
    "horizon",
    "category",
    "slot",
    "category_slot",
    "glyph",
    "named_check",
    "replayability_class",
    "measurement_status",
    "observation_count",
    "mean_residual",
    "mean_abs_residual",
    "hot_count",
    "cold_count",
    "neutral_count",
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
class ResidualAttributionSummaryRow:
    group_name: str
    group_value: str
    observation_count: int
    mean_residual: float
    mean_abs_residual: float
    hot_count: int
    cold_count: int
    neutral_count: int
    residual_attribution_run_id: str
    horizon: str | None = None
    category: str | None = None
    slot: int | None = None
    category_slot: str | None = None
    glyph: str | None = None
    named_check: str | None = None
    replayability_class: str | None = None
    measurement_status: str | None = None
    schema_version: str = RESIDUAL_ATTRIBUTION_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RESIDUAL_ATTRIBUTION_SUMMARY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported residual attribution summary schema version: "
                f"{self.schema_version}"
            )
        if not self.group_name.strip():
            raise ValueError("residual summary group_name is required")
        if not self.group_value.strip():
            raise ValueError("residual summary group_value is required")
        if self.observation_count <= 0:
            raise ValueError("residual summary observation_count must be positive")
        if (
            self.hot_count + self.cold_count + self.neutral_count
            != self.observation_count
        ):
            raise ValueError(
                "residual summary direction counts must equal observation_count"
            )
        if not self.residual_attribution_run_id.strip():
            raise ValueError("residual summary residual_attribution_run_id is required")

        if self.horizon is not None and self.horizon not in VALID_HORIZONS:
            raise ValueError(f"unsupported residual summary horizon: {self.horizon}")
        if self.category is not None and self.category not in {"A", "B", "C", "D", "E"}:
            raise ValueError(f"unsupported residual summary category: {self.category}")
        if self.slot is not None and not 1 <= self.slot <= 6:
            raise ValueError(f"unsupported residual summary slot: {self.slot}")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "group_name": self.group_name,
            "group_value": self.group_value,
            "horizon": self.horizon,
            "category": self.category,
            "slot": self.slot,
            "category_slot": self.category_slot,
            "glyph": self.glyph,
            "named_check": self.named_check,
            "replayability_class": self.replayability_class,
            "measurement_status": self.measurement_status,
            "observation_count": self.observation_count,
            "mean_residual": self.mean_residual,
            "mean_abs_residual": self.mean_abs_residual,
            "hot_count": self.hot_count,
            "cold_count": self.cold_count,
            "neutral_count": self.neutral_count,
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


def forecast_score_for_authoritative_row(
    row: AuthoritativeReplayDatasetRow,
) -> float:
    horizon = row.horizon.upper()
    if horizon == "H1":
        return row.h1_score
    if horizon == "H5":
        return row.h5_score
    raise ValueError(f"unsupported residual attribution horizon: {row.horizon}")


def build_residual_attribution_rows(
    authoritative_rows: Iterable[AuthoritativeReplayDatasetRow],
    *,
    residual_attribution_run_id: str = "residual-attribution",
) -> tuple[ResidualAttributionRow, ...]:
    residual_rows: list[ResidualAttributionRow] = []

    for row in sorted(authoritative_rows, key=_authoritative_residual_sort_key):
        if row.realized_outcome_status != REALIZED_OUTCOME_AVAILABLE:
            continue

        if row.target_date is None:
            raise ValueError("available residual attribution row requires target_date")
        if row.realized_current_score is None:
            raise ValueError(
                "available residual attribution row requires realized_current_score"
            )
        if row.realized_return is None:
            raise ValueError(
                "available residual attribution row requires realized_return"
            )

        forecast_score = forecast_score_for_authoritative_row(row)
        residual = round(forecast_score - row.realized_current_score, 8)

        residual_rows.append(
            ResidualAttributionRow(
                replay_date=row.replay_date,
                symbol=row.symbol,
                horizon=row.horizon,
                target_date=row.target_date,
                forecast_score=forecast_score,
                realized_current_score=row.realized_current_score,
                residual=residual,
                residual_direction=residual_direction(residual),
                realized_return=row.realized_return,
                category=row.category,
                slot=row.slot,
                glyph=row.glyph,
                named_check=row.named_check,
                check_score=row.check_score,
                replayability_class=row.replayability_class,
                measurement_status=row.measurement_status,
                source_module=row.source_module,
                function_name=row.function_name,
                audit_token=row.audit_token,
                dataset_run_id=row.dataset_run_id,
                authoritative_dataset_schema_version=row.schema_version,
                residual_attribution_run_id=residual_attribution_run_id,
            )
        )

    return tuple(residual_rows)


def _authoritative_residual_sort_key(
    row: AuthoritativeReplayDatasetRow,
) -> tuple[str, str, str, int, str, str, str]:
    target_date = "" if row.target_date is None else row.target_date.isoformat()
    return (
        row.replay_date.isoformat(),
        row.symbol,
        row.category,
        row.slot,
        row.horizon,
        target_date,
        row.named_check,
    )


DEFAULT_RESIDUAL_ATTRIBUTION_SUMMARY_GROUPS = (
    ("horizon",),
    ("horizon", "category"),
    ("horizon", "category_slot"),
    ("horizon", "category_slot", "glyph"),
    ("horizon", "named_check"),
    ("horizon", "replayability_class"),
    ("horizon", "measurement_status"),
)


def summarize_residual_attribution_rows(
    rows: Iterable[ResidualAttributionRow],
    *,
    groupings: Sequence[Sequence[str]] = DEFAULT_RESIDUAL_ATTRIBUTION_SUMMARY_GROUPS,
) -> tuple[ResidualAttributionSummaryRow, ...]:
    source_rows = tuple(rows)
    summaries: list[ResidualAttributionSummaryRow] = []

    for grouping in groupings:
        buckets: dict[tuple[object, ...], list[ResidualAttributionRow]] = defaultdict(
            list
        )
        for row in source_rows:
            key = tuple(_residual_group_value(row, field) for field in grouping)
            buckets[key].append(row)

        for key, bucket in sorted(buckets.items(), key=lambda item: item[0]):
            summaries.append(
                _build_residual_attribution_summary_row(grouping, key, bucket)
            )

    return tuple(summaries)


def _build_residual_attribution_summary_row(
    grouping: Sequence[str],
    key: tuple[object, ...],
    bucket: Sequence[ResidualAttributionRow],
) -> ResidualAttributionSummaryRow:
    residuals = [row.residual for row in bucket]
    count = len(bucket)
    first = bucket[0]
    group_values = dict(zip(grouping, key, strict=True))

    return ResidualAttributionSummaryRow(
        group_name="+".join(grouping),
        group_value="|".join(str(value) for value in key),
        horizon=_summary_field_value(group_values, "horizon"),
        category=_summary_field_value(group_values, "category"),
        slot=_summary_field_value(group_values, "slot"),
        category_slot=_summary_field_value(group_values, "category_slot"),
        glyph=_summary_field_value(group_values, "glyph"),
        named_check=_summary_field_value(group_values, "named_check"),
        replayability_class=_summary_field_value(group_values, "replayability_class"),
        measurement_status=_summary_field_value(group_values, "measurement_status"),
        observation_count=count,
        mean_residual=round(sum(residuals) / count, 8),
        mean_abs_residual=round(sum(abs(value) for value in residuals) / count, 8),
        hot_count=sum(row.residual_direction == RESIDUAL_HOT for row in bucket),
        cold_count=sum(row.residual_direction == RESIDUAL_COLD for row in bucket),
        neutral_count=sum(row.residual_direction == RESIDUAL_NEUTRAL for row in bucket),
        residual_attribution_run_id=first.residual_attribution_run_id,
    )


def _residual_group_value(row: ResidualAttributionRow, field: str) -> object:
    if field == "category_slot":
        return row.category_slot
    return getattr(row, field)


def _summary_field_value(
    group_values: dict[str, object],
    field: str,
) -> object | None:
    return group_values.get(field)


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
