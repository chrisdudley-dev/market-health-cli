"""market_health.trading_days

Weekend-only trading days (v0), with optional holiday-aware behavior.

Behavior:
- Always treats Sat/Sun as non-trading.
- If a local calendar file exists, also treats listed holidays as non-trading.
- If no calendar is available, behavior remains weekends-only (backwards compatible).

Calendar discovery:
- $JERBOA_CALENDAR_V1_PATH (preferred if set and exists)
- ~/.cache/jerboa/calendar.v1.json (fallback)
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Optional, Set, Union

DateLike = Union[dt.date, dt.datetime, str]

_DEFAULT_CAL_PATH = os.path.expanduser("~/.cache/jerboa/calendar.v1.json")
_ENV_CAL_PATH = "JERBOA_CALENDAR_V1_PATH"


def _as_date(x: DateLike) -> dt.date:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    if isinstance(x, str):
        return dt.date.fromisoformat(x.strip())
    raise TypeError(f"Unsupported DateLike: {type(x)}")


def _read_json(path: str) -> Optional[Any]:
    try:
        p = Path(path)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_date_str(s: Any) -> Optional[dt.date]:
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        return None


def _extract_holidays(obj: Any) -> Set[dt.date]:
    """
    Tolerant extraction:
    - {"holidays": ["YYYY-MM-DD", ...]}
    - {"market_holidays": [...]}
    - {"trading_holidays": [...]}
    - {"calendar": {"holidays": [...]}}
    - {"data": {"holidays": [...]}}
    """
    if not isinstance(obj, dict):
        return set()

    candidates = []
    for key in ("holidays", "market_holidays", "trading_holidays"):
        candidates.append(obj.get(key))

    cal = obj.get("calendar")
    if isinstance(cal, dict):
        candidates.append(cal.get("holidays"))

    data = obj.get("data")
    if isinstance(data, dict):
        candidates.append(data.get("holidays"))

    out: Set[dt.date] = set()
    for c in candidates:
        if isinstance(c, list):
            for item in c:
                d = _parse_date_str(item)
                if d:
                    out.add(d)
    return out


def _default_holidays() -> Set[dt.date]:
    path = os.environ.get(_ENV_CAL_PATH) or _DEFAULT_CAL_PATH
    obj = _read_json(path)
    return _extract_holidays(obj)


def is_trading_day(d: DateLike, *, holidays: Optional[Set[dt.date]] = None) -> bool:
    dd = _as_date(d)
    if dd.weekday() >= 5:
        return False
    if holidays and dd in holidays:
        return False
    return True


def next_trading_day(
    d: DateLike, *, holidays: Optional[Set[dt.date]] = None
) -> dt.date:
    """
    Roll forward to the next trading day (including today if already trading).
    """
    dd = _as_date(d)
    while not is_trading_day(dd, holidays=holidays):
        dd = dd + dt.timedelta(days=1)
    return dd


def add_trading_days(start: DateLike, trading_days: int) -> dt.date:
    """Add N trading days to start.

    - Start is rolled forward to a trading day.
    - N=0 returns the rolled-forward trading day.
    - N>0 returns the Nth trading day after that.
    """
    if trading_days < 0:
        raise ValueError("trading_days must be >= 0")

    holidays = _default_holidays()
    d0 = next_trading_day(start, holidays=holidays)

    d = d0
    for _ in range(trading_days):
        d = d + dt.timedelta(days=1)
        d = next_trading_day(d, holidays=holidays)
    return d
