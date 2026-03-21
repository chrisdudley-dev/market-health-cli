"""market_health.structure_engine

Deterministic structure sidecar scaffolding for floor/ceiling work.

This module is introduced as a non-invasive first step:
- define the canonical structure summary types
- provide a stable entrypoint for future integration
- add pure raw level generators without wiring them into engine/recommendations yet

Tracked by:
- #229 Create structure_engine.py module skeleton
- #230 Implement raw candidate level generators for v1
- #226 Freeze v1 structure fields and semantics
- #227 Resolve engine module naming and import paths
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import fmean, pstdev
from typing import Any


@dataclass(frozen=True)
class RawLevel:
    value: float
    kind: str
    source: str
    timeframe: str = "1d"
    label: str = ""


@dataclass(frozen=True)
class StructureZone:
    lower: float | None = None
    center: float | None = None
    upper: float | None = None
    weight: float | None = None


@dataclass(frozen=True)
class StructureSummary:
    version: str = "v1"
    symbol: str = ""
    as_of: str = ""
    price: float | None = None

    nearest_support_zone: StructureZone = field(default_factory=StructureZone)
    nearest_resistance_zone: StructureZone = field(default_factory=StructureZone)

    support_cushion_atr: float | None = None
    overhead_resistance_atr: float | None = None

    breakout_trigger: float | None = None
    breakdown_trigger: float | None = None
    reclaim_trigger: float | None = None

    breakout_quality_bucket: int | None = None
    breakdown_risk_bucket: int | None = None

    catastrophic_stop_candidate: float | None = None
    state_tags: tuple[str, ...] = ()

    tactical_stop_candidate: float | None = None
    stop_buy_candidate: float | None = None

    support_cushion_sigma: float | None = None
    overhead_resistance_sigma: float | None = None

    support_confluence_count: int | None = None
    resistance_confluence_count: int | None = None

    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "price": self.price,
            "nearest_support_zone": {
                "lower": self.nearest_support_zone.lower,
                "center": self.nearest_support_zone.center,
                "upper": self.nearest_support_zone.upper,
                "weight": self.nearest_support_zone.weight,
            },
            "nearest_resistance_zone": {
                "lower": self.nearest_resistance_zone.lower,
                "center": self.nearest_resistance_zone.center,
                "upper": self.nearest_resistance_zone.upper,
                "weight": self.nearest_resistance_zone.weight,
            },
            "support_cushion_atr": self.support_cushion_atr,
            "overhead_resistance_atr": self.overhead_resistance_atr,
            "breakout_trigger": self.breakout_trigger,
            "breakdown_trigger": self.breakdown_trigger,
            "reclaim_trigger": self.reclaim_trigger,
            "breakout_quality_bucket": self.breakout_quality_bucket,
            "breakdown_risk_bucket": self.breakdown_risk_bucket,
            "catastrophic_stop_candidate": self.catastrophic_stop_candidate,
            "state_tags": list(self.state_tags),
            "tactical_stop_candidate": self.tactical_stop_candidate,
            "stop_buy_candidate": self.stop_buy_candidate,
            "support_cushion_sigma": self.support_cushion_sigma,
            "overhead_resistance_sigma": self.overhead_resistance_sigma,
            "support_confluence_count": self.support_confluence_count,
            "resistance_confluence_count": self.resistance_confluence_count,
            "notes": list(self.notes),
        }


def empty_structure_summary(
    symbol: str, price: float | None = None
) -> StructureSummary:
    return StructureSummary(
        symbol=symbol,
        as_of=datetime.now(timezone.utc).isoformat(),
        price=price,
    )


def compute_structure_summary(
    symbol: str,
    *,
    price: float | None = None,
    context: dict[str, Any] | None = None,
) -> StructureSummary:
    """Return a placeholder structure summary."""
    _ = context
    return empty_structure_summary(symbol=symbol, price=price)


def generate_previous_bar_levels(
    *, high: float, low: float, timeframe: str = "1d"
) -> list[RawLevel]:
    return [
        RawLevel(
            value=low,
            kind="support",
            source="previous_bar",
            timeframe=timeframe,
            label="prev_low",
        ),
        RawLevel(
            value=high,
            kind="resistance",
            source="previous_bar",
            timeframe=timeframe,
            label="prev_high",
        ),
    ]


def generate_rolling_high_low_levels(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    windows: Sequence[int] = (5, 10, 20),
    timeframe: str = "1d",
) -> list[RawLevel]:
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have the same length")

    levels: list[RawLevel] = []
    for window in windows:
        if window <= 0 or len(highs) < window:
            continue
        levels.extend(
            [
                RawLevel(
                    value=min(lows[-window:]),
                    kind="support",
                    source="rolling_high_low",
                    timeframe=timeframe,
                    label=f"rolling_low_{window}",
                ),
                RawLevel(
                    value=max(highs[-window:]),
                    kind="resistance",
                    source="rolling_high_low",
                    timeframe=timeframe,
                    label=f"rolling_high_{window}",
                ),
            ]
        )
    return levels


def generate_classic_pivot_levels(
    *, high: float, low: float, close: float, timeframe: str = "1d"
) -> list[RawLevel]:
    pivot = (high + low + close) / 3.0
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)

    return [
        RawLevel(
            value=pivot,
            kind="reference",
            source="classic_pivot",
            timeframe=timeframe,
            label="pivot",
        ),
        RawLevel(
            value=s1,
            kind="support",
            source="classic_pivot",
            timeframe=timeframe,
            label="s1",
        ),
        RawLevel(
            value=s2,
            kind="support",
            source="classic_pivot",
            timeframe=timeframe,
            label="s2",
        ),
        RawLevel(
            value=s3,
            kind="support",
            source="classic_pivot",
            timeframe=timeframe,
            label="s3",
        ),
        RawLevel(
            value=r1,
            kind="resistance",
            source="classic_pivot",
            timeframe=timeframe,
            label="r1",
        ),
        RawLevel(
            value=r2,
            kind="resistance",
            source="classic_pivot",
            timeframe=timeframe,
            label="r2",
        ),
        RawLevel(
            value=r3,
            kind="resistance",
            source="classic_pivot",
            timeframe=timeframe,
            label="r3",
        ),
    ]


def _ema(values: Sequence[float], period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    ema = float(values[0])
    for value in values[1:]:
        ema = alpha * float(value) + (1.0 - alpha) * ema
    return ema


def generate_moving_average_levels(
    closes: Sequence[float],
    *,
    sma_periods: Sequence[int] = (50,),
    ema_periods: Sequence[int] = (20,),
    timeframe: str = "1d",
) -> list[RawLevel]:
    if not closes:
        return []

    levels: list[RawLevel] = []

    for period in sma_periods:
        if period > 0 and len(closes) >= period:
            levels.append(
                RawLevel(
                    value=fmean(closes[-period:]),
                    kind="reference",
                    source="moving_average",
                    timeframe=timeframe,
                    label=f"sma_{period}",
                )
            )

    for period in ema_periods:
        if period > 0 and len(closes) >= period:
            levels.append(
                RawLevel(
                    value=_ema(closes, period),
                    kind="reference",
                    source="moving_average",
                    timeframe=timeframe,
                    label=f"ema_{period}",
                )
            )

    return levels


def generate_anchored_vwap_levels(
    prices: Sequence[float],
    volumes: Sequence[float],
    *,
    anchor_index: int = 0,
    timeframe: str = "1d",
) -> list[RawLevel]:
    if len(prices) != len(volumes):
        raise ValueError("prices and volumes must have the same length")
    if not prices:
        return []
    if anchor_index < 0 or anchor_index >= len(prices):
        raise ValueError("anchor_index out of range")

    anchored_prices = prices[anchor_index:]
    anchored_volumes = volumes[anchor_index:]
    total_volume = float(sum(anchored_volumes))
    if total_volume <= 0:
        return []

    vwap = (
        sum(
            float(price) * float(volume)
            for price, volume in zip(anchored_prices, anchored_volumes, strict=False)
        )
        / total_volume
    )

    return [
        RawLevel(
            value=vwap,
            kind="reference",
            source="anchored_vwap",
            timeframe=timeframe,
            label=f"anchored_vwap_{anchor_index}",
        )
    ]


def generate_atr_band_levels(
    *,
    price: float,
    atr: float,
    multiples: Sequence[float] = (1.0,),
    timeframe: str = "1d",
) -> list[RawLevel]:
    if atr <= 0:
        return []

    levels: list[RawLevel] = []
    for multiple in multiples:
        if multiple <= 0:
            continue
        levels.extend(
            [
                RawLevel(
                    value=price - multiple * atr,
                    kind="support",
                    source="atr_band",
                    timeframe=timeframe,
                    label=f"atr_lower_{multiple:g}x",
                ),
                RawLevel(
                    value=price + multiple * atr,
                    kind="resistance",
                    source="atr_band",
                    timeframe=timeframe,
                    label=f"atr_upper_{multiple:g}x",
                ),
            ]
        )
    return levels


def generate_swing_levels(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    left: int = 2,
    right: int = 2,
    timeframe: str = "1d",
) -> list[RawLevel]:
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have the same length")
    if left < 1 or right < 1 or len(highs) < (left + right + 1):
        return []

    levels: list[RawLevel] = []
    for idx in range(left, len(highs) - right):
        high = highs[idx]
        low = lows[idx]

        left_highs = highs[idx - left : idx]
        right_highs = highs[idx + 1 : idx + right + 1]
        left_lows = lows[idx - left : idx]
        right_lows = lows[idx + 1 : idx + right + 1]

        if all(high > value for value in left_highs) and all(
            high >= value for value in right_highs
        ):
            levels.append(
                RawLevel(
                    value=high,
                    kind="resistance",
                    source="swing",
                    timeframe=timeframe,
                    label=f"swing_high_{idx}",
                )
            )

        if all(low < value for value in left_lows) and all(
            low <= value for value in right_lows
        ):
            levels.append(
                RawLevel(
                    value=low,
                    kind="support",
                    source="swing",
                    timeframe=timeframe,
                    label=f"swing_low_{idx}",
                )
            )

    return levels


def generate_donchian_levels(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    period: int = 20,
    timeframe: str = "1d",
) -> list[RawLevel]:
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have the same length")
    if period <= 0 or len(highs) < period:
        return []

    return [
        RawLevel(
            value=min(lows[-period:]),
            kind="support",
            source="donchian",
            timeframe=timeframe,
            label=f"donchian_lower_{period}",
        ),
        RawLevel(
            value=max(highs[-period:]),
            kind="resistance",
            source="donchian",
            timeframe=timeframe,
            label=f"donchian_upper_{period}",
        ),
    ]


def generate_bollinger_band_levels(
    closes: Sequence[float],
    *,
    period: int = 20,
    num_std: float = 2.0,
    timeframe: str = "1d",
) -> list[RawLevel]:
    if period <= 0 or len(closes) < period:
        return []

    window = [float(value) for value in closes[-period:]]
    mid = fmean(window)
    std = pstdev(window) if len(window) > 1 else 0.0

    return [
        RawLevel(
            value=mid - num_std * std,
            kind="support",
            source="bollinger",
            timeframe=timeframe,
            label=f"bollinger_lower_{period}",
        ),
        RawLevel(
            value=mid,
            kind="reference",
            source="bollinger",
            timeframe=timeframe,
            label=f"bollinger_mid_{period}",
        ),
        RawLevel(
            value=mid + num_std * std,
            kind="resistance",
            source="bollinger",
            timeframe=timeframe,
            label=f"bollinger_upper_{period}",
        ),
    ]
