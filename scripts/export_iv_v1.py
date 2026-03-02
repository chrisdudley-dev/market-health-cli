#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from market_health.providers.iv_provider import DEFAULT_CONFIG_PATH, load_iv_provider


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_symbols_csv(s: str) -> List[str]:
    out: List[str] = []
    for part in (s or "").split(","):
        sym = part.strip().upper()
        if sym:
            out.append(sym)
    return out


def _symbols_from_environment(env_path: Path) -> List[str]:
    if not env_path.exists():
        return []
    try:
        doc = _read_json(env_path)
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []
    sectors = doc.get("sectors")
    if not isinstance(sectors, list):
        return []
    out: List[str] = []
    for row in sectors:
        if not isinstance(row, dict):
            continue
        sym = row.get("symbol")
        if isinstance(sym, str) and sym.strip():
            out.append(sym.strip().upper())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export iv.v1.json to ~/.cache/jerboa (offline, provider boundary)."
    )
    ap.add_argument("--out", default=os.path.expanduser("~/.cache/jerboa/iv.v1.json"))
    ap.add_argument("--cache-dir", default=os.path.expanduser("~/.cache/jerboa"))
    ap.add_argument(
        "--symbols",
        default="",
        help="Comma-separated symbols. If empty, tries environment.v1.json.",
    )
    ap.add_argument(
        "--symbols-from", default="", help="Optional path to environment.v1.json"
    )
    ap.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="~/.config/jerboa/iv_provider.json",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cache_dir = Path(os.path.expanduser(args.cache_dir))
    out_p = Path(os.path.expanduser(args.out))
    env_p = (
        Path(os.path.expanduser(args.symbols_from))
        if args.symbols_from
        else (cache_dir / "environment.v1.json")
    )

    symbols = _parse_symbols_csv(str(args.symbols))
    if not symbols:
        symbols = _symbols_from_environment(env_p)
    if not symbols:
        symbols = ["SPY"]

    prov = load_iv_provider(os.path.expanduser(str(args.config)))
    bundle = prov.get_iv(symbols)

    doc: Dict[str, Any] = {
        "schema": bundle.schema,
        "status": bundle.status,
        "generated_at": bundle.generated_at,
        "source": bundle.source,
        "errors": list(bundle.errors),
        "points": [
            {
                "symbol": p.symbol,
                "iv": float(p.iv),
                "iv_rank_1y": float(p.iv_rank_1y),
                "iv_percentile_1y": float(p.iv_percentile_1y),
                "extra": dict(p.extra),
            }
            for p in bundle.points
        ],
    }

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.quiet:
        print(f"OK: wrote {out_p} status={bundle.status} points={len(bundle.points)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
