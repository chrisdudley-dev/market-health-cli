#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# allow running from repo without install
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from market_health.brokers.schwab_positions import (
    load_json,
    normalize_schwab_accounts_json,
)  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Import saved Schwab accounts JSON -> positions.v1.json (offline)"
    )
    ap.add_argument(
        "--in", dest="inp", required=True, help="Path to saved Schwab accounts JSON"
    )
    ap.add_argument(
        "--out",
        default=str(Path("/tmp") / "positions.v1.from_schwab.json"),
        help="Output positions.v1 path",
    )
    args = ap.parse_args()

    inp = os.path.expanduser(args.inp)
    outp = os.path.expanduser(args.out)

    raw = load_json(inp)
    doc = normalize_schwab_accounts_json(raw, source_path=inp)

    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")

    n = len(doc.get("positions") or [])
    print(f"OK: wrote positions.v1 (positions={n}) -> {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
