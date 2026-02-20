#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _err(errors: List[str], msg: str) -> None:
    errors.append(msg)


def validate(doc: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if doc.get("schema") != "recommendations.v1":
        _err(errors, 'schema must be "recommendations.v1"')

    if not isinstance(doc.get("asof"), str) or not doc.get("asof"):
        _err(errors, "asof must be a non-empty string")

    rec = doc.get("recommendation")
    if not isinstance(rec, dict):
        _err(errors, "recommendation must be an object")
        return errors

    action = rec.get("action")
    if action not in ("SWAP", "NOOP"):
        _err(errors, 'recommendation.action must be "SWAP" or "NOOP"')

    if not isinstance(rec.get("reason"), str) or not rec.get("reason"):
        _err(errors, "recommendation.reason must be a non-empty string")

    h = rec.get("horizon_trading_days")
    if not isinstance(h, int) or h < 0:
        _err(errors, "recommendation.horizon_trading_days must be an integer >= 0")

    t = rec.get("target_trade_date")
    if t is not None:
        if not isinstance(t, str):
            _err(errors, "recommendation.target_trade_date must be YYYY-MM-DD string or null")
        else:
            # Minimal YYYY-MM-DD shape check (full holiday semantics come later)
            import re
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", t):
                _err(errors, "recommendation.target_trade_date must match YYYY-MM-DD")

    ca = rec.get("constraints_applied")
    if not isinstance(ca, list) or not all(isinstance(x, str) for x in ca):
        _err(errors, "recommendation.constraints_applied must be a list of strings")

    if action == "SWAP":
        if not isinstance(rec.get("from_symbol"), str) or not rec.get("from_symbol"):
            _err(errors, "SWAP requires from_symbol (non-empty string)")
        if not isinstance(rec.get("to_symbol"), str) or not rec.get("to_symbol"):
            _err(errors, "SWAP requires to_symbol (non-empty string)")
        if rec.get("from_symbol") == rec.get("to_symbol"):
            _err(errors, "SWAP from_symbol and to_symbol must differ")
    else:
        # NOOP should not include swap fields (not fatal, but we warn via errors to keep contract clean)
        if "from_symbol" in rec or "to_symbol" in rec:
            _err(errors, "NOOP should not include from_symbol/to_symbol")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate recommendations.v1.json against the minimal contract")
    ap.add_argument("--path", required=True, help="Path to recommendations.v1.json")
    args = ap.parse_args()

    p = Path(args.path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    errors = validate(doc)

    if errors:
        print("ERR: recommendations.v1 validation failed:")
        for e in errors:
            print(" -", e)
        return 1

    print("OK: recommendations.v1 valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
