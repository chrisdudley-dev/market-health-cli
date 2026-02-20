#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from market_health.engine import compute_scores
from market_health.recommendations_engine import recommend


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> bool:
    """Write JSON only if content changed. Returns True if changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new_text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if old_text == new_text:
            return False

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)
    return True


def to_contract(rec_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure top-level recommendations.v1 envelope is correct."""
    if rec_doc.get("schema") != "recommendations.v1":
        raise ValueError("schema must be recommendations.v1")
    return rec_doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Export recommendations.v1.json to ~/.cache/jerboa/")
    ap.add_argument("--positions", default=os.path.expanduser("~/.cache/jerboa/positions.v1.json"))
    ap.add_argument("--out", default=os.path.expanduser("~/.cache/jerboa/recommendations.v1.json"))
    ap.add_argument("--sectors", nargs="*", default=None, help="Optional sector list (defaults to scoring engine defaults)")
    ap.add_argument("--period", default="6mo")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--min-improvement", type=float, default=0.10)
    ap.add_argument("--quiet", action="store_true")

    args = ap.parse_args()

    pos_p = Path(args.positions)
    out_p = Path(args.out)

    positions = read_json(pos_p) if pos_p.exists() else {"positions": []}

    # Compute scores (network call via yfinance). Exporter is allowed to do IO.
    score_rows: List[Dict[str, Any]] = compute_scores(
        sectors=args.sectors,
        period=args.period,
        interval=args.interval,
    )

    rec = recommend(
        positions=positions,
        scores=score_rows,
        constraints={
            "min_improvement_threshold": args.min_improvement,
            "horizon_trading_days": args.horizon,
        },
    )

    doc: Dict[str, Any] = {
        "schema": "recommendations.v1",
        "asof": utc_now_iso(),
        "generated_at": utc_now_iso(),
        "inputs": {
            "positions_path": str(pos_p),
            "period": args.period,
            "interval": args.interval,
            "horizon_trading_days": args.horizon,
            "min_improvement_threshold": args.min_improvement,
        },
        "recommendation": {
            "action": rec.action,
            "reason": rec.reason,
            "horizon_trading_days": rec.horizon_trading_days,
            "target_trade_date": rec.target_trade_date,
            "constraints_applied": list(rec.constraints_applied),
            "diagnostics": rec.diagnostics or {},
        },
    }

    if rec.action == "SWAP":
        doc["recommendation"]["from_symbol"] = rec.from_symbol
        doc["recommendation"]["to_symbol"] = rec.to_symbol

    doc = to_contract(doc)

    changed = atomic_write_json(out_p, doc)

    if not args.quiet:
        print(f"OK: wrote recommendations.v1 -> {out_p} (changed={changed}) action={rec.action}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
