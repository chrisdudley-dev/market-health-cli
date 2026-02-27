#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from market_health.calendar_v1 import build_calendar_v1, extract_events_and_holidays


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Export calendar.v1.json (offline)")
    ap.add_argument("--source", help="Optional JSON file containing events/holidays")
    ap.add_argument(
        "--out", default=os.path.expanduser("~/.cache/jerboa/calendar.v1.json")
    )
    ap.add_argument("--asof", help="YYYY-MM-DD (default: today)")
    ap.add_argument(
        "--horizons", default="1,5", help="Comma-separated horizons in trading days"
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    asof = date.fromisoformat(args.asof) if args.asof else date.today()
    horizons = tuple(int(x.strip()) for x in args.horizons.split(",") if x.strip())

    src_obj = _read_json(Path(args.source)) if args.source else None
    events, holidays = extract_events_and_holidays(src_obj)

    doc = build_calendar_v1(
        asof_date=asof,
        horizons_trading_days=horizons,
        events=events,
        holidays=holidays,
    )

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.quiet:
        by_h = doc["windows"]["by_h"]
        print(
            f"OK: wrote {out_p} horizons={sorted(by_h.keys(), key=int)} events={len(events)} holidays={len(holidays)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
