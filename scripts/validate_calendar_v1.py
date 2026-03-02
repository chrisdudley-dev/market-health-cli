#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def die(msg: str) -> None:
    raise SystemExit(f"ERR: {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate calendar.v1.json")
    ap.add_argument("--path", required=True)
    args = ap.parse_args()

    p = Path(args.path)
    doc = json.loads(p.read_text(encoding="utf-8"))

    if doc.get("schema") != "calendar.v1":
        die('schema must be "calendar.v1"')

    if not isinstance(doc.get("asof_date"), str):
        die("asof_date must be a string")
    if not isinstance(doc.get("holidays"), list):
        die("holidays must be a list")
    if not isinstance(doc.get("events"), list):
        die("events must be a list")

    w = doc.get("windows")
    if not isinstance(w, dict) or not isinstance(w.get("by_h"), dict):
        die("windows.by_h must be a dict")

    for h, win in w["by_h"].items():
        if not isinstance(h, str) or not isinstance(win, dict):
            die("windows.by_h keys must be strings and values dicts")
        if not isinstance(win.get("end_trade_date"), str):
            die(f"windows.by_h[{h}].end_trade_date must be string")

        for kind in ("earnings", "policy", "macro", "catalyst", "total"):
            if kind not in win:
                die(f"windows.by_h[{h}] missing {kind}")
            k = win[kind]
            if not isinstance(k, dict) or not isinstance(k.get("count"), int):
                die(f"windows.by_h[{h}].{kind}.count must be int")

    print("OK: calendar.v1 valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
