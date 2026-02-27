"""
cooldown_policy.py

Issue #112: Cooldown / anti-ping-pong enforcement.

Veto if the same swap pair (either direction) occurred within cooldown_trading_days.
Pure logic: caller supplies history events (already parsed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional, Tuple


@dataclass(frozen=True)
class SwapEvent:
    """A historical swap action."""

    ts: datetime
    from_symbol: str
    to_symbol: str
    target_trade_date: Optional[date] = None


@dataclass(frozen=True)
class CooldownResult:
    ok: bool
    vetoed: bool
    veto_reason: str
    matched_event: Optional[SwapEvent]


def _pair_key(a: str, b: str) -> Tuple[str, str]:
    # canonicalize directionless pair
    x, y = a.upper(), b.upper()
    return (x, y) if x <= y else (y, x)


def _days_between(d1: date, d2: date) -> int:
    return abs((d2 - d1).days)


def check_cooldown(
    *,
    proposed_from: str,
    proposed_to: str,
    history: Iterable[SwapEvent],
    cooldown_trading_days: int = 5,
    now_trade_date: Optional[date] = None,
) -> CooldownResult:
    """
    If now_trade_date is provided, compute distance using target_trade_date when available.
    Otherwise use timestamp dates.
    """
    if cooldown_trading_days <= 0:
        return CooldownResult(ok=True, vetoed=False, veto_reason="", matched_event=None)

    key = _pair_key(proposed_from, proposed_to)

    for ev in history:
        if _pair_key(ev.from_symbol, ev.to_symbol) != key:
            continue

        if now_trade_date and ev.target_trade_date:
            delta = _days_between(now_trade_date, ev.target_trade_date)
        elif now_trade_date:
            delta = _days_between(now_trade_date, ev.ts.date())
        else:
            delta = _days_between(date.today(), ev.ts.date())

        if delta <= cooldown_trading_days:
            return CooldownResult(
                ok=False,
                vetoed=True,
                veto_reason=f"cooldown:{delta}d<={cooldown_trading_days}d",
                matched_event=ev,
            )

    return CooldownResult(ok=True, vetoed=False, veto_reason="", matched_event=None)
