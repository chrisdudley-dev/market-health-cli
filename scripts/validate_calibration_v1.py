#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_health.calibration_v1 import validate_calibration_v1


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate calibration.v1.json")
    ap.add_argument("--path", required=True)
    args = ap.parse_args()

    doc = json.loads(Path(args.path).read_text(encoding="utf-8"))
    errors = validate_calibration_v1(doc)
    if errors:
        print("ERR: calibration.v1 validation failed:")
        for e in errors:
            print(f"- {e}")
        return 1

    print("OK: calibration.v1 valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
