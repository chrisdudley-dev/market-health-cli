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

    return tuple(
        sorted(
            rows,
            key=lambda row: (row.symbol, row.category, row.slot, row.horizon),
        )
    )


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
