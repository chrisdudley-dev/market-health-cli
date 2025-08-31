#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from typing import Dict, List

# Pull compute function + default sectors from your engine
from market_health.engine import compute_scores, SECTORS_DEFAULT


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute Market-Health scores and write JSON/CSV."
    )
    p.add_argument("--sectors", nargs="+", default=SECTORS_DEFAULT,
                   help="Tickers to score (default: sector SPDRs).")
    p.add_argument("--period", type=str, default="1y",
                   help="Lookback window for data fetch (e.g. 6mo, 1y).")
    p.add_argument("--interval", type=str, default="1d",
                   help="Data interval (e.g. 1d, 1h).")
    p.add_argument("--ttl", type=int, default=300,
                   help="In-process cache TTL (seconds) for data fetches.")
    p.add_argument("--out", type=str, default="scores.json",
                   help="Path to write JSON output (default: scores.json).")
    p.add_argument("--out-csv", type=str,
                   help="Optional CSV path to write category totals.")
    p.add_argument("--stdout", action="store_true",
                   help="Print JSON to stdout (still writes files if --out/--out-csv set).")
    p.add_argument("--pretty", action="store_true",
                   help="Pretty-print JSON with indentation.")
    p.add_argument("--watch", type=int,
                   help="Recompute and write every N seconds until Ctrl+C.")
    return p.parse_args()


def _category_total(cat_node: dict) -> int:
    """Safely sum scores in a category node: {'checks': [{'label','score'}, ...]}."""
    checks = cat_node.get("checks", [])
    try:
        return sum(int(c.get("score", 0)) for c in checks)
    except Exception:
        return 0


def _as_csv_rows(payload: List[Dict]) -> List[List[str]]:
    """
    Convert compute_scores() JSON into simple rows:
    [symbol, A, B, C, D, E, F, total]
    """
    rows: List[List[str]] = [["symbol", "A", "B", "C", "D", "E", "F", "total"]]
    for item in payload:
        sym = item.get("symbol", "?")
        cats = item.get("categories", {})

        a = _category_total(cats.get("A", {}))
        b = _category_total(cats.get("B", {}))
        c = _category_total(cats.get("C", {}))
        d = _category_total(cats.get("D", {}))
        e = _category_total(cats.get("E", {}))
        f = _category_total(cats.get("F", {}))
        total = a + b + c + d + e + f

        rows.append([sym, str(a), str(b), str(c), str(d), str(e), str(f), str(total)])
    return rows


def _write_once(args: argparse.Namespace) -> None:
    # 1) compute
    data = compute_scores(
        sectors=args.sectors,
        period=args.period,
        interval=args.interval,
        ttl_sec=args.ttl,
    )

    # 2) JSON (file + optionally stdout)
    if args.pretty:
        json_text = json.dumps(data, indent=2)
    else:
        json_text = json.dumps(data, separators=(",", ":"))

    if args.stdout:
        print(json_text)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(json_text)
        print(f"Wrote JSON: {args.out}")

    # 3) CSV (optional)
    if args.out_csv:
        rows = _as_csv_rows(data)
        with open(args.out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        print(f"Wrote CSV:  {args.out_csv}")

    sys.stdout.flush()


def main() -> None:
    args = parse_args()

    # single-shot
    if not args.watch:
        _write_once(args)
        return

    # looped mode
    try:
        while True:
            _write_once(args)
            time.sleep(max(1, int(args.watch)))
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
