#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_health.golden_fixtures_v1 import generate_golden_fixtures_v1


def main() -> int:
    ap = argparse.ArgumentParser(description="Write golden fixtures for Issue #117")
    ap.add_argument("--out-dir", default="tests/fixtures")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fx = generate_golden_fixtures_v1()

    (out_dir / "golden.forecast_scores.v1.json").write_text(
        json.dumps(fx["forecast"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "golden.recommendation.forecast.v1.json").write_text(
        json.dumps(fx["recommendation"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"OK: wrote fixtures into {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
