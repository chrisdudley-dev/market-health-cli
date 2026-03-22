from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RiskOverlayState:
    symbol: str
    armed: bool
    catastrophic_stop: float | None
    breach_level: float | None
    status: str
    reason: str
    source: str = "structure_summary"


def _f(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def build_risk_overlay_state(
    *,
    symbol: str,
    structure_summary: dict[str, Any] | None,
) -> RiskOverlayState:
    ss = structure_summary if isinstance(structure_summary, dict) else {}

    catastrophic_stop = _f(ss.get("catastrophic_stop_candidate"))
    breakdown_trigger = _f(ss.get("breakdown_trigger"))
    support_cushion_atr = _f(ss.get("support_cushion_atr"))

    if catastrophic_stop is None:
        return RiskOverlayState(
            symbol=symbol,
            armed=False,
            catastrophic_stop=None,
            breach_level=None,
            status="UNAVAILABLE",
            reason="No catastrophic stop candidate available from structure summary.",
        )

    if support_cushion_atr is not None and support_cushion_atr <= 0.5:
        return RiskOverlayState(
            symbol=symbol,
            armed=True,
            catastrophic_stop=catastrophic_stop,
            breach_level=breakdown_trigger
            if breakdown_trigger is not None
            else catastrophic_stop,
            status="ARMED",
            reason="Support cushion is tight; catastrophic overlay armed.",
        )

    return RiskOverlayState(
        symbol=symbol,
        armed=False,
        catastrophic_stop=catastrophic_stop,
        breach_level=breakdown_trigger
        if breakdown_trigger is not None
        else catastrophic_stop,
        status="DISARMED",
        reason="Catastrophic stop candidate exists, but overlay is not armed.",
    )
