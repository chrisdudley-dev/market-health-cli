from __future__ import annotations

import datetime as dt
from typing import Union

DateLike = Union[dt.date, dt.datetime]


def _to_date(x: DateLike) -> dt.date:
    return x.date() if isinstance(x, dt.datetime) else x


def is_trading_day(d: dt.date) -> bool:
    """v0: weekends-only (Mon-Fri are trading days)."""
    return d.weekday() < 5


def next_trading_day(d: dt.date) -> dt.date:
    """Roll forward to the next trading day (including today if already trading)."""
    while not is_trading_day(d):
        d += dt.timedelta(days=1)
    return d


def add_trading_days(start: DateLike, trading_days: int) -> dt.date:
    """Add N trading days to start.

    Semantics (v0):
    - Weekends are non-trading.
    - Start is rolled forward to a trading day.
    - N=0 returns the rolled-forward trading day.
    - N>0 returns the Nth trading day after that.

    This ensures outputs are always trading days.
    """
    if trading_days < 0:
        raise ValueError("trading_days must be >= 0")

    d = next_trading_day(_to_date(start))
    if trading_days == 0:
        return d

    added = 0
    while added < trading_days:
        d += dt.timedelta(days=1)
        if is_trading_day(d):
            added += 1
    return d
