#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List


def _err(errors: List[str], msg: str) -> None:
    errors.append(msg)


def validate_positions_v1(doc: Any) -> List[str]:
    errors: List[str] = []

    if not isinstance(doc, dict):
        _err(errors, "top-level must be an object")
        return errors

    if doc.get("schema") != "positions.v1":
        _err(errors, 'schema must be "positions.v1"')

    positions = doc.get("positions")
    if not isinstance(positions, list):
        _err(errors, "positions must be an array")
        return errors

    for i, p in enumerate(positions):
        if not isinstance(p, dict):
            _err(errors, f"positions[{i}] must be an object")
            continue

        asset_type = p.get("asset_type")
        if asset_type not in ("equity", "option", "other"):
            _err(errors, f'positions[{i}].asset_type must be "equity"|"option"|"other"')

        symbol = p.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            _err(errors, f"positions[{i}].symbol must be a non-empty string")

        for k in (
            "qty",
            "avg_price",
            "mark_price",
            "market_value",
            "cost_basis",
            "unrealized_pl",
            "strike",
        ):
            if k in p and not isinstance(p.get(k), (int, float)):
                _err(errors, f"positions[{i}].{k} must be a number if present")

        if asset_type == "option":
            right = p.get("right")
            if right is not None and right not in ("C", "P"):
                _err(errors, f'positions[{i}].right must be "C"|"P" if present')

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate positions.v1.json against the minimal positions.v1 contract"
    )
    ap.add_argument(
        "--path",
        default=os.path.expanduser("~/.cache/jerboa/positions.v1.json"),
        help="Path to positions.v1.json",
    )
    args = ap.parse_args()

    p = os.path.expanduser(args.path)
    try:
        raw = open(p, "r", encoding="utf-8").read()
    except FileNotFoundError:
        print(f"ERR: file not found: {p}", file=sys.stderr)
        return 2

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERR: invalid JSON: {e}", file=sys.stderr)
        return 2

    errors = validate_positions_v1(doc)
    if errors:
        print("ERR: positions.v1 validation failed:")
        for e in errors[:50]:
            print(f"- {e}")
        if len(errors) > 50:
            print(f"... and {len(errors) - 50} more")
        return 1

    n = len(doc.get("positions") or [])
    print(f"OK: positions.v1 valid (positions={n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
