"""market_health.structure_engine

Deterministic structure sidecar scaffolding for floor/ceiling work.

This module is introduced as a non-invasive first step:
- define the canonical structure summary types
- provide a stable entrypoint for future integration
- avoid changing current engine/recommendation behavior until later issues

Tracked by:
- #229 Create structure_engine.py module skeleton
- #226 Freeze v1 structure fields and semantics
- #227 Resolve engine module naming and import paths
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


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
    """Return a placeholder structure summary.

    This intentionally does not compute any real levels yet.
    Follow-up issues will add candidate generation, normalization,
    clustering, and downstream integration.
    """
    _ = context
    return empty_structure_summary(symbol=symbol, price=price)
