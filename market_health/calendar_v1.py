from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

CALENDAR_V1_SCHEMA = "calendar.v1"

_DEFAULT_CAL_PATH = os.path.expanduser("~/.cache/jerboa/calendar.v1.json")
_ENV_CAL_PATH = "JERBOA_CALENDAR_V1_PATH"

_KINDS = ("earnings", "policy", "macro", "catalyst")


def default_calendar_path() -> str:
    return os.environ.get(_ENV_CAL_PATH) or _DEFAULT_CAL_PATH


def _read_json(path: str) -> Optional[Any]:
    try:
        p = Path(path)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_calendar_v1(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    obj = _read_json(path or default_calendar_path())
    return obj if isinstance(obj, dict) else None


def _as_date(x: Any) -> Optional[dt.date]:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        try:
            return dt.date.fromisoformat(s)
        except Exception:
            return None
    return None


def _normalize_kind(x: Any) -> str:
    if not isinstance(x, str):
        return "catalyst"
    k = x.strip().lower()
    if k in _KINDS:
        return k
    # tolerant synonyms
    if k in ("rates", "fed", "fomc"):
        return "policy"
    if k in ("cpi", "ppi", "jobs", "nfp", "gdp", "inflation"):
        return "macro"
    if k in ("earn", "earnings_date", "earnings-call"):
        return "earnings"
    return "catalyst"


def _extract_list(obj: Any, *keys: str) -> List[Any]:
    if not isinstance(obj, dict):
        return []
    for k in keys:
        v = obj.get(k)
        if isinstance(v, list):
            return v
    return []


def extract_events_and_holidays(obj: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Accepts:
      - {"events":[...], "holidays":[...]}
      - {"calendar":{"events":[...], "holidays":[...]}}
      - raw list[...] treated as events
    """
    if obj is None:
        return ([], [])

    events_raw: List[Any] = []
    holidays_raw: List[Any] = []

    if isinstance(obj, list):
        events_raw = obj
    elif isinstance(obj, dict):
        events_raw = _extract_list(obj, "events")
        holidays_raw = _extract_list(
            obj, "holidays", "market_holidays", "trading_holidays"
        )

        cal = obj.get("calendar")
        if isinstance(cal, dict):
            if not events_raw:
                events_raw = _extract_list(cal, "events")
            if not holidays_raw:
                holidays_raw = _extract_list(cal, "holidays")
    else:
        return ([], [])

    # holidays -> iso dates (dedup/sorted)
    hol_set: Set[str] = set()
    for h in holidays_raw:
        d = _as_date(h)
        if d:
            hol_set.add(d.isoformat())

    # events -> normalized dicts
    events: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str]] = set()

    for e in events_raw:
        if isinstance(e, dict):
            d = _as_date(e.get("date") or e.get("day") or e.get("when"))
            if not d:
                continue
            kind = _normalize_kind(e.get("kind") or e.get("type") or e.get("category"))
            symbol = (e.get("symbol") or "") if isinstance(e.get("symbol"), str) else ""
            title = (
                (e.get("title") or e.get("name") or "")
                if isinstance((e.get("title") or e.get("name")), str)
                else ""
            )
        elif isinstance(e, str):
            # tolerate raw "YYYY-MM-DD" as a generic catalyst marker
            d = _as_date(e)
            if not d:
                continue
            kind, symbol, title = "catalyst", "", ""
        else:
            continue

        key = (d.isoformat(), kind, symbol.strip().upper(), title.strip())
        if key in seen:
            continue
        seen.add(key)

        events.append(
            {
                "date": key[0],
                "kind": kind,
                "symbol": key[2],
                "title": key[3],
            }
        )

    events.sort(
        key=lambda x: (
            x["date"],
            x["kind"],
            x.get("symbol") or "",
            x.get("title") or "",
        )
    )
    holidays = sorted(hol_set)
    return (events, holidays)


def _is_trading_day(d: dt.date, holidays: Set[dt.date]) -> bool:
    if d.weekday() >= 5:
        return False
    if d in holidays:
        return False
    return True


def _roll_to_trading_day(d: dt.date, holidays: Set[dt.date]) -> dt.date:
    while not _is_trading_day(d, holidays):
        d = d + dt.timedelta(days=1)
    return d


def add_trading_days_with_holidays(
    start: dt.date, trading_days: int, holidays: Set[dt.date]
) -> dt.date:
    """
    Start is rolled forward to a trading day.
    N=0 returns the rolled-forward day.
    N>0 returns the Nth trading day after that.
    """
    if trading_days < 0:
        raise ValueError("trading_days must be >= 0")

    d = _roll_to_trading_day(start, holidays)
    if trading_days == 0:
        return d

    left = trading_days
    while left > 0:
        d = d + dt.timedelta(days=1)
        if _is_trading_day(d, holidays):
            left -= 1
    return d


def build_calendar_v1(
    *,
    asof_date: dt.date,
    horizons_trading_days: Sequence[int] = (1, 5),
    events: Sequence[Dict[str, Any]] = (),
    holidays: Sequence[str] = (),
) -> Dict[str, Any]:
    """
    windows.by_h[h] uses an *end_trade_date* computed in trading days.
    Events are counted if: asof_date < event_date <= end_trade_date
    (so holidays/weekends inside the window still count).
    """
    asof = _as_date(asof_date)
    if asof is None:
        raise TypeError("asof_date must be a date")

    hol_set: Set[dt.date] = set()
    for h in holidays:
        d = _as_date(h)
        if d:
            hol_set.add(d)

    # normalize incoming events (assume already normalized but tolerate)
    norm_events: List[Dict[str, Any]] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        d = _as_date(e.get("date"))
        if not d:
            continue
        norm_events.append(
            {
                "date": d.isoformat(),
                "kind": _normalize_kind(e.get("kind")),
                "symbol": (e.get("symbol") or "").strip().upper()
                if isinstance(e.get("symbol"), str)
                else "",
                "title": (e.get("title") or "").strip()
                if isinstance(e.get("title"), str)
                else "",
            }
        )
    norm_events.sort(
        key=lambda x: (
            x["date"],
            x["kind"],
            x.get("symbol") or "",
            x.get("title") or "",
        )
    )

    windows_by_h: Dict[str, Any] = {}
    for h in horizons_trading_days:
        h_int = int(h)
        end_trade = add_trading_days_with_holidays(asof, h_int, hol_set)
        end_iso = end_trade.isoformat()

        # filter window
        window_events = [
            e for e in norm_events if asof.isoformat() < e["date"] <= end_iso
        ]

        def _bucket(kind: str) -> Dict[str, Any]:
            evs = [e for e in window_events if e["kind"] == kind]
            next_date = min((e["date"] for e in evs), default=None)
            syms = sorted({e.get("symbol") for e in evs if e.get("symbol")})
            return {"count": len(evs), "next_date": next_date, "symbols": syms}

        total_next = min((e["date"] for e in window_events), default=None)
        windows_by_h[str(h_int)] = {
            "end_trade_date": end_iso,
            "earnings": _bucket("earnings"),
            "policy": _bucket("policy"),
            "macro": _bucket("macro"),
            "catalyst": _bucket("catalyst"),
            "total": {"count": len(window_events), "next_date": total_next},
        }

    return {
        "schema": CALENDAR_V1_SCHEMA,
        "asof_date": asof.isoformat(),
        "horizons_trading_days": [int(h) for h in horizons_trading_days],
        "holidays": sorted(d.isoformat() for d in hol_set),
        "events": norm_events,
        "windows": {"by_h": windows_by_h},
    }
