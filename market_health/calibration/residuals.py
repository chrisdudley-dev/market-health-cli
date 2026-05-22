from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date

from market_health.calibration.schema import ReplayArtifactRow

RESIDUAL_SCHEMA_VERSION = "calibration_forecast_residual.v1"

VALID_HORIZONS = ("H1", "H5")


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
