import json
from datetime import date

from market_health.calendar_v1 import build_calendar_v1


def test_calendar_v1_windows_counts(tmp_path):
    # asof: 2025-12-31 (Wed)
    # holiday: 2026-01-01
    # events:
    # - policy on 2026-01-01 (holiday)
    # - earnings on 2026-01-02 (trading day)
    doc = build_calendar_v1(
        asof_date=date(2025, 12, 31),
        horizons_trading_days=(1, 5),
        holidays=["2026-01-01"],
        events=[
            {"date": "2026-01-01", "kind": "policy", "title": "FOMC minutes"},
            {
                "date": "2026-01-02",
                "kind": "earnings",
                "symbol": "AAPL",
                "title": "AAPL earnings",
            },
        ],
    )

    assert doc["schema"] == "calendar.v1"
    assert "windows" in doc and "by_h" in doc["windows"]

    h1 = doc["windows"]["by_h"]["1"]
    # +1 trading day from 2025-12-31 ends 2026-01-02 (skips holiday as trading day),
    # but the window includes calendar days up to that end_trade_date (so 1/1 counts).
    assert h1["total"]["count"] == 2
    assert h1["policy"]["count"] == 1
    assert h1["earnings"]["count"] == 1

    p = tmp_path / "calendar.v1.json"
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reread = json.loads(p.read_text(encoding="utf-8"))
    assert reread["windows"]["by_h"]["1"]["total"]["count"] == 2
