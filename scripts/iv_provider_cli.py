#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path as _Path

# allow running from repo checkout without installing the package
_REPO_ROOT = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from market_health.providers.iv_provider import DEFAULT_CONFIG_PATH, load_iv_provider  # noqa: E402

def main() -> int:
    ap = argparse.ArgumentParser(description="IV provider boundary (Category D)")
    ap.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to local provider config JSON")
    ap.add_argument("--symbols", default="SPY,AAPL", help="Comma-separated symbols")
    ap.add_argument("--status", action="store_true", help="Print provider status only")
    ap.add_argument("--print", dest="do_print", action="store_true", help="Print normalized iv.v1 JSON")
    args = ap.parse_args()

    syms = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    p = load_iv_provider(os.path.expanduser(args.config))
    b = p.get_iv(syms)

    if args.status and not args.do_print:
        print(f"status={b.status} points={len(b.points)} config={os.path.expanduser(args.config)}")
        return 0

    out = {
        "schema": b.schema,
        "status": b.status,
        "generated_at": b.generated_at,
        "source": b.source,
        "points": [
            {
                "symbol": pt.symbol,
                "metrics": {
                    "iv": pt.iv,
                    "iv_rank_1y": pt.iv_rank_1y,
                    "iv_percentile_1y": pt.iv_percentile_1y,
                },
                "extra": pt.extra,
            }
            for pt in b.points
        ],
        "errors": b.errors,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
