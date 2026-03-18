#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
del _Path

# EXPORT_ENVIRONMENT_V1_SYS_PATH: ensure repo root on sys.path for local runs


import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from market_health.engine import compute_scores, SECTORS_DEFAULT
from market_health.market_catalog import get_symbol_meta

MAX_PER_CATEGORY = 12
MAX_TOTAL = MAX_PER_CATEGORY * 6


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _safe_int(x: Any, lo: int = 0, hi: int = 2) -> int:
    try:
        v = int(x)
    except Exception:
        v = 0
    return max(lo, min(hi, v))


def _sector_totals(item: Dict[str, Any]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    cats = item.get("categories", {}) or {}
    for key in "ABCDEF":
        node = cats.get(key, {}) or {}
        checks = node.get("checks", []) or []
        s = 0
        for ch in checks:
            s += _safe_int((ch or {}).get("score", 0), 0, 2)
        totals[key] = s
    return totals


def _band_3(pct: int) -> str:
    # 3-color banding consistent with the “simple widget” concept:
    # 0–39 = RED, 40–59 = YELLOW, 60–100 = GREEN
    if pct >= 60:
        return "GREEN"
    if pct >= 40:
        return "YELLOW"
    return "RED"


def _attach_market_metadata_rows(rows):
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            out.append(row)
            continue

        new_row = dict(row)
        sym = (
            new_row.get("symbol") or new_row.get("ticker") or new_row.get("underlying")
        )

        if isinstance(sym, str) and sym.strip():
            meta = get_symbol_meta(sym)
            if meta is not None:
                if new_row.get("market") is None:
                    new_row["market"] = meta.market
                if new_row.get("region") is None:
                    new_row["region"] = meta.region
                if new_row.get("kind") is None:
                    new_row["kind"] = meta.kind
                if new_row.get("bucket_id") is None:
                    new_row["bucket_id"] = meta.bucket_id
                if new_row.get("family_id") is None:
                    new_row["family_id"] = meta.family_id
                if new_row.get("benchmark_symbol") is None:
                    new_row["benchmark_symbol"] = meta.benchmark_symbol
                if new_row.get("calendar_id") is None:
                    new_row["calendar_id"] = meta.calendar_id
                if new_row.get("currency") is None:
                    new_row["currency"] = meta.currency
                if new_row.get("taxonomy") is None:
                    new_row["taxonomy"] = meta.taxonomy

        out.append(new_row)
    return out


def main() -> int:
    p = argparse.ArgumentParser(
        description="Export Market Health environment output (environment.v1.json)"
    )
    p.add_argument(
        "--out", default=str(Path.home() / ".cache/jerboa/environment.v1.json")
    )
    p.add_argument(
        "--legacy",
        default=str(Path.home() / ".cache/jerboa/market_health.sectors.json"),
    )
    p.add_argument("--period", default="6mo")
    p.add_argument("--interval", default="1d")
    p.add_argument("--ttl-sec", type=int, default=3600)
    p.add_argument(
        "--sectors",
        nargs="*",
        default=None,
        help="Override sectors (defaults to engine SECTORS_DEFAULT)",
    )
    args = p.parse_args()

    out_path = Path(os.path.expanduser(args.out))
    legacy_path = Path(os.path.expanduser(args.legacy))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)

    sectors = args.sectors if args.sectors else list(SECTORS_DEFAULT)

    payload: List[Dict[str, Any]] = compute_scores(
        sectors=sectors,
        period=args.period,
        interval=args.interval,
        ttl_sec=args.ttl_sec,
    )
    payload = _attach_market_metadata_rows(payload)

    sectors_out: List[Dict[str, Any]] = []
    legacy_out: List[Dict[str, Any]] = []

    for item in payload:
        sym = item.get("symbol", item.get("ticker", "?"))
        totals = _sector_totals(item)
        total = sum(totals.values())
        pct = int(round((total / MAX_TOTAL) * 100)) if MAX_TOTAL else 0
        pct = max(0, min(100, pct))

        sectors_out.append(
            {
                "symbol": sym,
                "market": item.get("market"),
                "region": item.get("region"),
                "kind": item.get("kind"),
                "bucket_id": item.get("bucket_id"),
                "family_id": item.get("family_id"),
                "benchmark_symbol": item.get("benchmark_symbol"),
                "calendar_id": item.get("calendar_id"),
                "currency": item.get("currency"),
                "taxonomy": item.get("taxonomy"),
                "band": _band_3(pct),
                "pct": pct,
                "total": total,
                "max_total": MAX_TOTAL,
                "buckets": totals,
                "bands": totals,
                # Keep the underlying check structure for deeper views:
                "categories": (item.get("categories") or {}),
            }
        )

        # Legacy shape: list of items with symbol + categories (what your current JSON loader expects)
        legacy_out.append(
            {
                "symbol": sym,
                "market": item.get("market"),
                "region": item.get("region"),
                "kind": item.get("kind"),
                "bucket_id": item.get("bucket_id"),
                "family_id": item.get("family_id"),
                "benchmark_symbol": item.get("benchmark_symbol"),
                "calendar_id": item.get("calendar_id"),
                "currency": item.get("currency"),
                "taxonomy": item.get("taxonomy"),
                "categories": (item.get("categories") or {}),
            }
        )

    env = {
        "schema": "environment.v1",
        "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": {"git_rev": _git_rev()},
        "sectors": sectors_out,
    }

    out_path.write_text(
        json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    legacy_path.write_text(
        json.dumps(legacy_out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"OK: wrote {out_path}")
    print(f"OK: wrote {legacy_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
