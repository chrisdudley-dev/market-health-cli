#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict

from market_health.calibration_v1 import build_calibration_v1

DEFAULT_OUT = os.path.expanduser("~/.cache/jerboa/calibration.v1.json")


def _parse_kv_float(items: list[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for s in items:
        if "=" not in s:
            raise SystemExit(f"ERR: invalid override '{s}' (expected key=value)")
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            raise SystemExit(f"ERR: invalid override '{s}' (empty key)")
        try:
            out[k] = float(v)
        except Exception:
            raise SystemExit(f"ERR: invalid override '{s}' (value must be number)")
    return out


def _parse_kv_any(items: list[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for s in items:
        if "=" not in s:
            raise SystemExit(f"ERR: invalid override '{s}' (expected key=value)")
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            raise SystemExit(f"ERR: invalid override '{s}' (empty key)")
        # best-effort typing: int -> float -> str
        try:
            out[k] = int(v)
        except Exception:
            try:
                out[k] = float(v)
            except Exception:
                out[k] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export calibration.v1 defaults for forecast-mode tuning"
    )
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Output path (default: ~/.cache/jerboa/calibration.v1.json)",
    )
    ap.add_argument("--asof", help="YYYY-MM-DD (default: today)")
    ap.add_argument(
        "--threshold",
        action="append",
        default=[],
        help="Override threshold: key=value (repeatable)",
    )
    ap.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="Override constraint: key=value (repeatable)",
    )
    ap.add_argument("--notes", default=None, help="Optional notes string")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    asof = date.fromisoformat(args.asof) if args.asof else date.today()
    th = _parse_kv_float(args.threshold)
    cs = _parse_kv_any(args.constraint)

    doc = build_calibration_v1(
        asof_date=asof, thresholds=th or None, constraints=cs or None, notes=args.notes
    )

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.quiet:
        print(f"OK: wrote {out_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
