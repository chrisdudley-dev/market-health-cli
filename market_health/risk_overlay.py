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


def confirm_overlay_breach(
    *,
    overlay: RiskOverlayState,
    close_price: float | None,
    prior_close_price: float | None = None,
    confirm_closes: int = 2,
) -> bool:
    if not overlay.armed:
        return False
    if overlay.breach_level is None:
        return False
    if not isinstance(close_price, (int, float)):
        return False

    level = float(overlay.breach_level)
    latest_breach = float(close_price) < level
    if not latest_breach:
        return False

    if confirm_closes <= 1:
        return True

    if not isinstance(prior_close_price, (int, float)):
        return False

    return float(prior_close_price) < level


def build_confirmed_risk_overlay_state(
    *,
    symbol: str,
    structure_summary: dict[str, Any] | None,
    close_price: float | None,
    prior_close_price: float | None = None,
    confirm_closes: int = 2,
) -> RiskOverlayState:
    base = build_risk_overlay_state(
        symbol=symbol,
        structure_summary=structure_summary,
    )

    if not base.armed:
        return base

    breached = confirm_overlay_breach(
        overlay=base,
        close_price=close_price,
        prior_close_price=prior_close_price,
        confirm_closes=confirm_closes,
    )

    if not breached:
        return base

    return RiskOverlayState(
        symbol=base.symbol,
        armed=True,
        catastrophic_stop=base.catastrophic_stop,
        breach_level=base.breach_level,
        status="BREACHED",
        reason="Confirmed catastrophic breach below overlay level.",
        source=base.source,
    )
