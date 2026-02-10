#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path as _Path

# allow running from repo checkout without installing
_REPO_ROOT = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from market_health.providers.flow_provider import (  # noqa: E402
    DEFAULT_FLOW_CONFIG,
    StubFlowProvider,
    load_flow_provider,
)

def main() -> int:
    ap = argparse.ArgumentParser(description="FlowProvider helper (Category C provider boundary)")
    ap.add_argument("--config", default=DEFAULT_FLOW_CONFIG, help="~/.config/jerboa/flow_provider.json")
    ap.add_argument("--status", action="store_true", help="Show provider status (no network)")
    ap.add_argument("--stub-path", default="", help="Normalize a stub fixture JSON (no config needed)")
    ap.add_argument("--symbols", default="", help="Comma-separated symbols (optional)")
    args = ap.parse_args()

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if args.stub_path:
        prov = StubFlowProvider(args.stub_path)
        batch = prov.get_flow(syms)
        print(json.dumps(batch.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.status:
        prov = load_flow_provider(args.config)
        print(f"provider={prov.describe()}")
        batch = prov.get_flow(syms)
        print(f"status={batch.status} points={len(batch.points)}")
        return 0

    ap.print_help()
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
