import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd


def load_mod():
    path = Path("scripts/export_recommendations_v1.py")
    spec = importlib.util.spec_from_file_location("export_recommendations_v1", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def fake_schedule(rows):
    idx = pd.Index([pd.Timestamp(session) for session, _, _ in rows])
    return pd.DataFrame(
        {
            "market_open": [pd.Timestamp(open_ts) for _, open_ts, _ in rows],
            "market_close": [pd.Timestamp(close_ts) for _, _, close_ts in rows],
        },
        index=idx,
    )


class FakeCal:
    def __init__(self, sched):
        self._sched = sched

    def schedule(self, start_date=None, end_date=None):
        return self._sched


def freeze_now(mod, monkeypatch, now_iso):
    real_datetime = datetime

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            dt = real_datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
            if tz is not None:
                return dt.astimezone(tz)
            return dt

        @classmethod
        def fromisoformat(cls, s):
            return real_datetime.fromisoformat(s)

        @classmethod
        def combine(cls, date, time, tzinfo=None):
            return real_datetime.combine(date, time, tzinfo=tzinfo)

    monkeypatch.setattr(mod, "datetime", FrozenDateTime)


def patch_calendar(mod, monkeypatch, rows):
    sched = fake_schedule(rows)

    class FakeMcal:
        @staticmethod
        def get_calendar(name):
            assert name == "NYSE"
            return FakeCal(sched)

    monkeypatch.setitem(__import__("sys").modules, "pandas_market_calendars", FakeMcal)


def test_regular_session_uses_rolling_ttl(monkeypatch):
    mod = load_mod()
    freeze_now(mod, monkeypatch, "2026-03-13T15:00:00+00:00")
    patch_calendar(
        mod,
        monkeypatch,
        [
            ("2026-03-13", "2026-03-13T14:30:00+00:00", "2026-03-13T21:00:00+00:00"),
        ],
    )

    assert mod._is_market_session_fresh("2026-03-13T14:50:00Z", 15) is True
    assert mod._is_market_session_fresh("2026-03-13T14:40:00Z", 15) is False
    assert mod._is_same_or_last_completed_session("2026-03-13T18:00:00Z") is True
    assert mod._is_same_or_last_completed_session("2026-03-12T20:00:00Z") is False


def test_premarket_accepts_last_completed_session(monkeypatch):
    mod = load_mod()
    freeze_now(mod, monkeypatch, "2026-03-13T12:00:00+00:00")
    patch_calendar(
        mod,
        monkeypatch,
        [
            ("2026-03-12", "2026-03-12T14:30:00+00:00", "2026-03-12T21:00:00+00:00"),
            ("2026-03-13", "2026-03-13T14:30:00+00:00", "2026-03-13T21:00:00+00:00"),
        ],
    )

    assert mod._is_market_session_fresh("2026-03-13T11:55:00Z", 15) is True
    assert mod._is_same_or_last_completed_session("2026-03-12T19:31:32Z") is True
    assert mod._is_same_or_last_completed_session("2026-03-11T19:31:32Z") is False


def test_weekend_accepts_friday_session(monkeypatch):
    mod = load_mod()
    freeze_now(mod, monkeypatch, "2026-03-14T15:00:00+00:00")
    patch_calendar(
        mod,
        monkeypatch,
        [
            ("2026-03-13", "2026-03-13T14:30:00+00:00", "2026-03-13T21:00:00+00:00"),
            ("2026-03-16", "2026-03-16T13:30:00+00:00", "2026-03-16T20:00:00+00:00"),
        ],
    )

    assert mod._is_same_or_last_completed_session("2026-03-13T19:31:32Z") is True
    assert mod._is_same_or_last_completed_session("2026-03-12T19:31:32Z") is False


def test_holiday_accepts_last_trading_session(monkeypatch):
    mod = load_mod()
    freeze_now(mod, monkeypatch, "2026-02-16T15:00:00+00:00")
    patch_calendar(
        mod,
        monkeypatch,
        [
            ("2026-02-13", "2026-02-13T14:30:00+00:00", "2026-02-13T21:00:00+00:00"),
            ("2026-02-17", "2026-02-17T14:30:00+00:00", "2026-02-17T21:00:00+00:00"),
        ],
    )

    assert mod._is_same_or_last_completed_session("2026-02-13T19:31:32Z") is True
    assert mod._is_same_or_last_completed_session("2026-02-12T19:31:32Z") is False
