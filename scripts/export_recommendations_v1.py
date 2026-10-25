"""Historical session freshness helpers; recommendation export is retired."""

from datetime import datetime, timezone, timedelta
from typing import Any


def _parse_iso_utc(value: Any):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_market_calendar_module():
    try:
        import pandas_market_calendars as mcal

        return mcal
    except ModuleNotFoundError:
        return None


def _is_market_session_fresh(value: Any, max_age_minutes: int = 15):
    dt = _parse_iso_utc(value)
    if dt is None:
        return False

    if max_age_minutes <= 0:
        return True

    now_utc = datetime.now(timezone.utc)
    ttl_seconds = max_age_minutes * 60

    def _within_ttl() -> bool:
        age = (now_utc - dt).total_seconds()
        return 0 <= age <= ttl_seconds

    # Live broker/cache inputs that were just refreshed should be accepted
    # regardless of market-session timing. Session-aware logic below is only
    # needed for accepting the last completed market session outside intraday TTL.
    if _within_ttl():
        return True

    try:
        from zoneinfo import ZoneInfo

        session_tz = ZoneInfo("America/New_York")
    except Exception:
        session_tz = timezone(timedelta(hours=-5), "ET")

    mcal = _get_market_calendar_module()

    if mcal is None:
        now_et = now_utc.astimezone(session_tz)
        dt_et = dt.astimezone(session_tz)

        open_mins = 9 * 60 + 30
        close_mins = 16 * 60
        now_mins = now_et.hour * 60 + now_et.minute
        is_weekday = now_et.weekday() < 5

        if is_weekday and open_mins <= now_mins <= close_mins:
            return dt_et.date() == now_et.date() and _within_ttl()

        if is_weekday and now_mins < open_mins:
            if dt_et.date() == now_et.date() and _within_ttl():
                return True

        return _is_same_or_last_completed_session(value)

    sched = mcal.get_calendar("NYSE").schedule(
        start_date=(now_utc - timedelta(days=10)).date().isoformat(),
        end_date=(now_utc + timedelta(days=2)).date().isoformat(),
    )
    if sched.empty:
        return False

    rows = []
    for idx, row in sched.iterrows():
        open_ts = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        close_ts = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        session_label = str(idx.date() if hasattr(idx, "date") else idx)
        rows.append((session_label, open_ts, close_ts))

    for _, open_ts, close_ts in rows:
        if open_ts <= now_utc <= close_ts:
            return open_ts <= dt <= close_ts and _within_ttl()

    future_rows = [r for r in rows if r[1] > now_utc]
    if future_rows:
        next_open = future_rows[0][1]
        now_local = now_utc.astimezone(session_tz)
        dt_local = dt.astimezone(session_tz)
        next_open_local = next_open.astimezone(session_tz)

        if now_utc < next_open and now_local.date() == next_open_local.date():
            if dt_local.date() == now_local.date() and _within_ttl():
                return True

    return _is_same_or_last_completed_session(value)


def _is_same_or_last_completed_session(value: Any):
    dt = _parse_iso_utc(value)
    if dt is None:
        return False

    now_utc = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        session_tz = ZoneInfo("America/New_York")
    except Exception:
        session_tz = timezone(timedelta(hours=-5), "ET")

    dt_session = dt.astimezone(session_tz).date().isoformat()
    mcal = _get_market_calendar_module()

    if mcal is None:
        try:
            from zoneinfo import ZoneInfo

            et_tz = ZoneInfo("America/New_York")
        except Exception:
            et_tz = timezone(timedelta(hours=-5), "ET")

        now_et = now_utc.astimezone(et_tz)
        dt_et = dt.astimezone(et_tz)

        def _last_weekday(d):
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        mins_now = now_et.hour * 60 + now_et.minute
        open_mins = 9 * 60 + 30

        ref_date = now_et.date()
        if now_et.weekday() < 5 and mins_now < open_mins:
            ref_date -= timedelta(days=1)
        ref_date = _last_weekday(ref_date)
        return dt_et.date() == ref_date

    sched = mcal.get_calendar("NYSE").schedule(
        start_date=(now_utc - timedelta(days=10)).date().isoformat(),
        end_date=(now_utc + timedelta(days=2)).date().isoformat(),
    )
    if sched.empty:
        return False

    rows = []
    for idx, row in sched.iterrows():
        open_ts = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        close_ts = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        session_label = str(idx.date() if hasattr(idx, "date") else idx)
        rows.append((session_label, open_ts, close_ts))

    # If market is currently live, accept the current session.
    for session_label, open_ts, close_ts in rows:
        if open_ts <= now_utc <= close_ts:
            return dt_session == session_label

    # Otherwise accept the most recent completed scheduled session.
    prior_rows = [r for r in rows if r[2] <= now_utc]
    if not prior_rows:
        return False

    last_completed_session = prior_rows[-1][0]
    return dt_session == last_completed_session


if __name__ == "__main__":
    raise SystemExit(
        "Legacy recommendation export retired; use market-health --refresh --out policy.json"
    )
