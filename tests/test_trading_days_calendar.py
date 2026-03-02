import json
from datetime import date

from market_health.trading_days import add_trading_days


def test_add_trading_days_skips_holiday(tmp_path, monkeypatch):
    cal = {
        "schema": "calendar.v1",
        "holidays": ["2026-01-01"],  # New Year's Day
    }
    cal_p = tmp_path / "calendar.v1.json"
    cal_p.write_text(json.dumps(cal), encoding="utf-8")
    monkeypatch.setenv("JERBOA_CALENDAR_V1_PATH", str(cal_p))

    # 2025-12-31 is Wed. +1 trading day would normally be 2026-01-01,
    # but that is a holiday, so it should roll to 2026-01-02.
    got = add_trading_days(date(2025, 12, 31), 1)
    assert got.isoformat() == "2026-01-02"

    # Start on a holiday should roll forward even for N=0
    got0 = add_trading_days("2026-01-01", 0)
    assert got0.isoformat() == "2026-01-02"
