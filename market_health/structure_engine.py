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

from collections.abc import Mapping, Sequence
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
class NormalizedLevel:
    raw_level: RawLevel
    distance_atr: float | None = None
    distance_sigma: float | None = None


@dataclass(frozen=True)
class StructureZone:
    lower: float | None = None
    center: float | None = None
    upper: float | None = None
    weight: float | None = None


@dataclass(frozen=True)
class ClusteredZone:
    kind: str
    lower: float
    center: float
    upper: float
    weight: float
    count: int
    labels: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()


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


def _structure_zone_from_cluster(zone: ClusteredZone | None) -> StructureZone:
    if zone is None:
        return StructureZone()
    return StructureZone(
        lower=zone.lower,
        center=zone.center,
        upper=zone.upper,
        weight=zone.weight,
    )


def _select_nearest_support_zone(
    zones: Sequence[ClusteredZone], *, price: float | None
) -> ClusteredZone | None:
    supports = [zone for zone in zones if zone.kind == "support"]
    if not supports:
        return None
    if price is None:
        return max(supports, key=lambda zone: zone.center)
    eligible = [zone for zone in supports if zone.center <= price]
    if eligible:
        return min(eligible, key=lambda zone: abs(price - zone.center))
    return max(supports, key=lambda zone: zone.center)


def _select_nearest_resistance_zone(
    zones: Sequence[ClusteredZone], *, price: float | None
) -> ClusteredZone | None:
    resistances = [zone for zone in zones if zone.kind == "resistance"]
    if not resistances:
        return None
    if price is None:
        return min(resistances, key=lambda zone: zone.center)
    eligible = [zone for zone in resistances if zone.center >= price]
    if eligible:
        return min(eligible, key=lambda zone: abs(zone.center - price))
    return min(resistances, key=lambda zone: zone.center)


def _infer_zone_width(
    *,
    price: float | None,
    atr: float | None,
    realized_vol: float | None,
    explicit_zone_width: float | None = None,
) -> float:
    if explicit_zone_width is not None and explicit_zone_width > 0:
        return float(explicit_zone_width)

    atr_component = 0.25 * float(atr) if atr is not None and atr > 0 else 0.0
    sigma_component = (
        0.5 * float(price) * float(realized_vol)
        if price is not None
        and realized_vol is not None
        and price > 0
        and realized_vol > 0
        else 0.0
    )
    return max(atr_component, sigma_component, 0.01)


def _breakout_quality_bucket(
    *,
    support_cushion_atr: float | None,
    overhead_resistance_atr: float | None,
) -> int:
    if overhead_resistance_atr is None:
        return 0
    if overhead_resistance_atr <= 0.5 and (
        support_cushion_atr is None or support_cushion_atr >= 0.5
    ):
        return 2
    if overhead_resistance_atr <= 1.5:
        return 1
    return 0


def _breakdown_risk_bucket(*, support_cushion_atr: float | None) -> int:
    if support_cushion_atr is None:
        return 0
    if support_cushion_atr <= 0.5:
        return 2
    if support_cushion_atr <= 1.5:
        return 1
    return 0


def _state_tags(
    *,
    price: float | None,
    support_zone: ClusteredZone | None,
    support_cushion_atr: float | None,
    overhead_resistance_atr: float | None,
    breakout_quality_bucket: int,
) -> tuple[str, ...]:
    tags: list[str] = []

    if support_cushion_atr is not None and support_cushion_atr <= 0.5:
        tags.append("near_damage_zone")
    if overhead_resistance_atr is not None and overhead_resistance_atr <= 0.5:
        tags.append("overhead_heavy")
    if breakout_quality_bucket == 2:
        tags.append("breakout_ready")
    if price is not None and support_zone is not None and support_zone.upper >= price:
        tags.append("reclaim_ready")

    return tuple(tags)


def empty_structure_summary(
    symbol: str,
    price: float | None = None,
    *,
    as_of: str | None = None,
) -> StructureSummary:
    return StructureSummary(
        symbol=symbol,
        as_of=as_of or datetime.now(timezone.utc).isoformat(),
        price=price,
    )


def compute_structure_summary(
    symbol: str,
    *,
    price: float | None = None,
    context: dict[str, Any] | None = None,
) -> StructureSummary:
    """Compute a minimal structure summary artifact from existing helpers."""
    context = context or {}
    timeframe = str(context.get("timeframe", "1d"))
    as_of = context.get("as_of")

    previous_bar = context.get("previous_bar") or {}
    highs = context.get("highs") or []
    lows = context.get("lows") or []
    closes = context.get("closes") or []
    prices = context.get("prices") or closes
    volumes = context.get("volumes") or []

    if price is None:
        price = context.get("price")
    if price is None and closes:
        price = float(closes[-1])

    atr = context.get("atr")
    realized_vol = context.get("realized_vol")
    close_for_sigma = context.get("close_for_sigma", price)

    raw_levels: list[RawLevel] = []

    prev_high = previous_bar.get("high")
    prev_low = previous_bar.get("low")
    prev_close = previous_bar.get("close")

    if prev_high is not None and prev_low is not None:
        raw_levels.extend(
            generate_previous_bar_levels(
                high=float(prev_high),
                low=float(prev_low),
                timeframe=timeframe,
            )
        )

    if prev_high is not None and prev_low is not None and prev_close is not None:
        raw_levels.extend(
            generate_classic_pivot_levels(
                high=float(prev_high),
                low=float(prev_low),
                close=float(prev_close),
                timeframe=timeframe,
            )
        )

    if highs and lows:
        raw_levels.extend(
            generate_rolling_high_low_levels(
                highs=highs,
                lows=lows,
                windows=tuple(context.get("rolling_windows", (5, 10, 20))),
                timeframe=timeframe,
            )
        )
        raw_levels.extend(
            generate_swing_levels(
                highs=highs,
                lows=lows,
                left=int(context.get("swing_left", 2)),
                right=int(context.get("swing_right", 2)),
                timeframe=timeframe,
            )
        )
        raw_levels.extend(
            generate_donchian_levels(
                highs=highs,
                lows=lows,
                period=int(context.get("donchian_period", 20)),
                timeframe=timeframe,
            )
        )

    if closes:
        raw_levels.extend(
            generate_moving_average_levels(
                closes=closes,
                sma_periods=tuple(context.get("sma_periods", (50,))),
                ema_periods=tuple(context.get("ema_periods", (20,))),
                timeframe=timeframe,
            )
        )
        raw_levels.extend(
            generate_bollinger_band_levels(
                closes=closes,
                period=int(context.get("bollinger_period", 20)),
                num_std=float(context.get("bollinger_num_std", 2.0)),
                timeframe=timeframe,
            )
        )

    if prices and volumes and len(prices) == len(volumes):
        raw_levels.extend(
            generate_anchored_vwap_levels(
                prices=prices,
                volumes=volumes,
                anchor_index=int(context.get("anchor_index", 0)),
                timeframe=timeframe,
            )
        )

    if price is not None and atr is not None:
        raw_levels.extend(
            generate_atr_band_levels(
                price=float(price),
                atr=float(atr),
                multiples=tuple(context.get("atr_multiples", (1.0,))),
                timeframe=timeframe,
            )
        )

    normalized_levels = normalize_raw_levels(
        raw_levels,
        price=price,
        atr=atr,
        close=close_for_sigma,
        realized_vol=realized_vol,
    )

    zones = cluster_raw_levels_into_zones(
        raw_levels,
        zone_width=_infer_zone_width(
            price=price,
            atr=atr,
            realized_vol=realized_vol,
            explicit_zone_width=context.get("zone_width"),
        ),
        source_weights=context.get("source_weights"),
        timeframe_weights=context.get("timeframe_weights"),
    )

    support_zone = _select_nearest_support_zone(zones, price=price)
    resistance_zone = _select_nearest_resistance_zone(zones, price=price)

    support_edge = support_zone.upper if support_zone is not None else None
    resistance_edge = resistance_zone.upper if resistance_zone is not None else None

    support_cushion_atr_raw = normalize_distance_atr(
        price=price,
        level=support_edge,
        atr=atr,
    )
    support_cushion_atr = (
        None
        if support_cushion_atr_raw is None
        else max(float(support_cushion_atr_raw), 0.0)
    )

    overhead_resistance_atr_raw = (
        None
        if price is None or resistance_edge is None or atr is None or atr <= 0
        else (float(resistance_edge) - float(price)) / float(atr)
    )
    overhead_resistance_atr = (
        None
        if overhead_resistance_atr_raw is None
        else max(float(overhead_resistance_atr_raw), 0.0)
    )

    support_cushion_sigma_raw = normalize_distance_sigma(
        price=price,
        level=support_edge,
        close=close_for_sigma,
        realized_vol=realized_vol,
    )
    support_cushion_sigma = (
        None
        if support_cushion_sigma_raw is None
        else max(float(support_cushion_sigma_raw), 0.0)
    )

    overhead_resistance_sigma_raw = (
        None
        if (
            price is None
            or resistance_edge is None
            or close_for_sigma is None
            or realized_vol is None
            or close_for_sigma <= 0
            or realized_vol <= 0
        )
        else (float(resistance_edge) - float(price)) / (float(close_for_sigma) * float(realized_vol))
    )
    overhead_resistance_sigma = (
        None
        if overhead_resistance_sigma_raw is None
        else max(float(overhead_resistance_sigma_raw), 0.0)
    )

    breakout_quality_bucket = _breakout_quality_bucket(
        support_cushion_atr=support_cushion_atr,
        overhead_resistance_atr=overhead_resistance_atr,
    )
    breakdown_risk_bucket = _breakdown_risk_bucket(
        support_cushion_atr=support_cushion_atr,
    )

    return StructureSummary(
        symbol=symbol,
        as_of=as_of or datetime.now(timezone.utc).isoformat(),
        price=price,
        nearest_support_zone=_structure_zone_from_cluster(support_zone),
        nearest_resistance_zone=_structure_zone_from_cluster(resistance_zone),
        support_cushion_atr=support_cushion_atr,
        overhead_resistance_atr=overhead_resistance_atr,
        breakout_trigger=None if resistance_zone is None else resistance_zone.upper,
        breakdown_trigger=None if support_zone is None else support_zone.lower,
        reclaim_trigger=None if support_zone is None else support_zone.upper,
        breakout_quality_bucket=breakout_quality_bucket,
        breakdown_risk_bucket=breakdown_risk_bucket,
        catastrophic_stop_candidate=None
        if support_zone is None
        else support_zone.lower,
        state_tags=_state_tags(
            price=price,
            support_zone=support_zone,
            support_cushion_atr=support_cushion_atr,
            overhead_resistance_atr=overhead_resistance_atr,
            breakout_quality_bucket=breakout_quality_bucket,
        ),
        tactical_stop_candidate=None if support_zone is None else support_zone.lower,
        stop_buy_candidate=None if resistance_zone is None else resistance_zone.upper,
        support_cushion_sigma=support_cushion_sigma,
        overhead_resistance_sigma=overhead_resistance_sigma,
        support_confluence_count=None if support_zone is None else support_zone.count,
        resistance_confluence_count=None
        if resistance_zone is None
        else resistance_zone.count,
        notes=(
            f"raw_levels={len(raw_levels)}",
            f"normalized_levels={len(normalized_levels)}",
        ),
    )


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


def normalize_distance_atr(
    *, price: float | None, level: float | None, atr: float | None
) -> float | None:
    if price is None or level is None or atr is None or atr <= 0:
        return None
    return (float(price) - float(level)) / float(atr)


def normalize_distance_sigma(
    *,
    price: float | None,
    level: float | None,
    close: float | None,
    realized_vol: float | None,
) -> float | None:
    if (
        price is None
        or level is None
        or close is None
        or realized_vol is None
        or close <= 0
        or realized_vol <= 0
    ):
        return None

    denom = float(close) * float(realized_vol)
    if denom <= 0:
        return None
    return (float(price) - float(level)) / denom


def normalize_raw_level(
    raw_level: RawLevel,
    *,
    price: float | None,
    atr: float | None,
    close: float | None,
    realized_vol: float | None,
) -> NormalizedLevel:
    return NormalizedLevel(
        raw_level=raw_level,
        distance_atr=normalize_distance_atr(
            price=price,
            level=raw_level.value,
            atr=atr,
        ),
        distance_sigma=normalize_distance_sigma(
            price=price,
            level=raw_level.value,
            close=close,
            realized_vol=realized_vol,
        ),
    )


def normalize_raw_levels(
    raw_levels: Sequence[RawLevel],
    *,
    price: float | None,
    atr: float | None,
    close: float | None,
    realized_vol: float | None,
) -> list[NormalizedLevel]:
    return [
        normalize_raw_level(
            raw_level,
            price=price,
            atr=atr,
            close=close,
            realized_vol=realized_vol,
        )
        for raw_level in raw_levels
    ]


def _raw_level_weight(
    raw_level: RawLevel,
    *,
    source_weights: Mapping[str, float] | None = None,
    timeframe_weights: Mapping[str, float] | None = None,
) -> float:
    source_weight = (
        1.0
        if source_weights is None
        else float(source_weights.get(raw_level.source, 1.0))
    )
    timeframe_weight = (
        1.0
        if timeframe_weights is None
        else float(timeframe_weights.get(raw_level.timeframe, 1.0))
    )
    weight = source_weight * timeframe_weight
    return weight if weight > 0 else 0.0


def _finalize_cluster(
    raw_levels: Sequence[RawLevel],
    *,
    source_weights: Mapping[str, float] | None = None,
    timeframe_weights: Mapping[str, float] | None = None,
) -> ClusteredZone:
    if not raw_levels:
        raise ValueError("raw_levels must not be empty")

    weights = [
        _raw_level_weight(
            raw_level,
            source_weights=source_weights,
            timeframe_weights=timeframe_weights,
        )
        for raw_level in raw_levels
    ]
    total_weight = sum(weights)

    if total_weight > 0:
        center = (
            sum(
                raw_level.value * weight
                for raw_level, weight in zip(raw_levels, weights, strict=False)
            )
            / total_weight
        )
        zone_weight = total_weight
    else:
        center = fmean(raw_level.value for raw_level in raw_levels)
        zone_weight = float(len(raw_levels))

    return ClusteredZone(
        kind=raw_levels[0].kind,
        lower=min(raw_level.value for raw_level in raw_levels),
        center=center,
        upper=max(raw_level.value for raw_level in raw_levels),
        weight=zone_weight,
        count=len(raw_levels),
        labels=tuple(
            sorted(raw_level.label for raw_level in raw_levels if raw_level.label)
        ),
        sources=tuple(sorted({raw_level.source for raw_level in raw_levels})),
        timeframes=tuple(sorted({raw_level.timeframe for raw_level in raw_levels})),
    )


def cluster_raw_levels_into_zones(
    raw_levels: Sequence[RawLevel],
    *,
    zone_width: float,
    source_weights: Mapping[str, float] | None = None,
    timeframe_weights: Mapping[str, float] | None = None,
) -> list[ClusteredZone]:
    if zone_width <= 0:
        raise ValueError("zone_width must be positive")

    zones: list[ClusteredZone] = []

    for kind in ("support", "resistance"):
        filtered = sorted(
            (raw_level for raw_level in raw_levels if raw_level.kind == kind),
            key=lambda raw_level: raw_level.value,
        )
        if not filtered:
            continue

        current_cluster: list[RawLevel] = [filtered[0]]

        for raw_level in filtered[1:]:
            current_upper = max(item.value for item in current_cluster)
            if raw_level.value - current_upper <= zone_width:
                current_cluster.append(raw_level)
            else:
                zones.append(
                    _finalize_cluster(
                        current_cluster,
                        source_weights=source_weights,
                        timeframe_weights=timeframe_weights,
                    )
                )
                current_cluster = [raw_level]

        zones.append(
            _finalize_cluster(
                current_cluster,
                source_weights=source_weights,
                timeframe_weights=timeframe_weights,
            )
        )

    return zones
