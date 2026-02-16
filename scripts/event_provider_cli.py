#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path as _Path

# Allow running from repo checkout without installing the package
_REPO_ROOT = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from market_health.providers.event_provider import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    NullEventProvider,
    StubEventProvider,
    load_event_provider,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Category A events provider helper (offline stub + null)"
    )
    ap.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to local provider config JSON",
    )
    ap.add_argument("--symbols", default="SPY,AAPL", help="Comma-separated symbols")
    ap.add_argument("--status", action="store_true", help="Print provider status only")
    ap.add_argument("--use-stub", default="", help="Force stub path (bypasses config)")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    if args.use_stub:
        prov = StubEventProvider(args.use_stub)
        prov_name = f"stub({args.use_stub})"
    else:
        prov = load_event_provider(args.config)
        prov_name = prov.__class__.__name__

    if args.status:
        if isinstance(prov, NullEventProvider):
            print(f"provider=null (no provider configured) config={args.config}")
        else:
            print(f"provider={prov_name} config={args.config}")
        return 0

    b = prov.get_events(symbols)
    out = {
        "schema": b.schema,
        "status": b.status,
        "generated_at": b.generated_at,
        "source": b.source,
        "points": [
            {
                "ts": p.ts,
                "symbol": p.symbol,
                "type": p.type,
                "headline": p.headline,
                "impact": p.impact,
                "confidence": p.confidence,
                "extra": p.extra,
            }
            for p in b.points
        ],
        "errors": b.errors,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
