#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from market_health.engine import SECTORS_DEFAULT, safe_download


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _pick_field(frame: pd.DataFrame, key: str, ticker: str) -> Optional[pd.Series]:
    if frame is None or frame.empty:
        return None
    if key in frame.columns:
        return pd.to_numeric(frame[key], errors="coerce")
    if isinstance(frame.columns, pd.MultiIndex):
        if (key, ticker) in frame.columns:
            return pd.to_numeric(frame[(key, ticker)], errors="coerce")
        lvl0 = frame.columns.get_level_values(0)
        if key in set(lvl0):
            for col in frame.columns:
                if isinstance(col, tuple) and col[0] == key:
                    return pd.to_numeric(frame[col], errors="coerce")
    norm = {str(c).strip().title(): c for c in frame.columns}
    if key.title() in norm:
        return pd.to_numeric(frame[norm[key.title()]], errors="coerce")
    return None


def _series_to_list(s: Optional[pd.Series]) -> Optional[List[float]]:
    if s is None:
        return None
    vals = pd.to_numeric(s, errors="coerce").dropna().tolist()
    if not vals:
        return None
    return [float(v) for v in vals]


def _row_from_frame(sym: str, frame: pd.DataFrame) -> Optional[Dict[str, Any]]:
    close = _series_to_list(_pick_field(frame, "Close", sym))
    if not close:
        return None

    row: Dict[str, Any] = {
        "symbol": sym,
        "close": close,
    }

    high = _series_to_list(_pick_field(frame, "High", sym))
    low = _series_to_list(_pick_field(frame, "Low", sym))
    volume = _series_to_list(_pick_field(frame, "Volume", sym))

    if high:
        row["high"] = high
    if low:
        row["low"] = low
    if volume:
        row["volume"] = volume

    return row


def build_ohlcv_doc(
    symbols: Iterable[str],
    *,
    period: str = "1y",
    interval: str = "1d",
    ttl_sec: int = 300,
    data: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, Any]:
    order: List[str] = []
    for sym in list(symbols) + ["SPY"]:
        s = str(sym).strip().upper()
        if s and s not in order:
            order.append(s)

    frames = (
        data
        if data is not None
        else safe_download(order, period=period, interval=interval, ttl_sec=ttl_sec)
    )

    rows: List[Dict[str, Any]] = []
    for sym in order:
        row = _row_from_frame(sym, frames.get(sym, pd.DataFrame()))
        if row is not None:
            rows.append(row)

    return {
        "schema": "ohlcv.sectors.v1",
        "generated_at": utc_now(),
        "symbols": order,
        "rows": rows,
    }


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        old_text = path.read_text(encoding="utf-8", errors="replace")
        if old_text == new_text:
            return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export OHLCV cache for sector forecast inputs"
    )
    ap.add_argument(
        "--out", default=os.path.expanduser("~/.cache/jerboa/ohlcv.sectors.v1.json")
    )
    ap.add_argument("--period", default="1y")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--ttl-sec", type=int, default=300)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out_p = Path(args.out)
    doc = build_ohlcv_doc(
        SECTORS_DEFAULT or [],
        period=args.period,
        interval=args.interval,
        ttl_sec=args.ttl_sec,
    )
    changed = atomic_write_json(out_p, doc)
    if not args.quiet:
        print(f"OK: wrote {out_p} changed={changed} symbols={len(doc['rows'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
