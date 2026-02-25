#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from market_health.engine import compute_scores
from market_health.recommendations_engine import recommend
from market_health.trading_days import add_trading_days
from market_health.ledger import append_event
import json


def _load_swaps_today() -> tuple[str, int, Path]:
    """Return (today_iso, swaps_today, state_path). Resilient to missing/invalid state."""
    home_root = Path(os.environ.get("JERBOA_HOME_WIN") or os.path.expanduser("~"))
    state_p = (
        home_root
        / ".cache"
        / "jerboa"
        / "state"
        / "recommendations_swaps_today.v1.json"
    )
    state_p.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    swaps_today = 0
    try:
        if state_p.exists():
            st = json.loads(state_p.read_text(encoding="utf-8"))
            if isinstance(st, dict) and st.get("date") == today:
                swaps_today = int(st.get("count", 0) or 0)
    except Exception:
        swaps_today = 0
    return today, swaps_today, state_p


def _bump_swaps_today(*, today: str, swaps_today: int, state_p: Path) -> None:
    try:
        state = {"date": today, "count": swaps_today + 1}
        state_p.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except Exception:
        pass


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
    ap = argparse.ArgumentParser(
        description="Export recommendations.v1.json to ~/.cache/jerboa/"
    )
    ap.add_argument(
        "--positions", default=os.path.expanduser("~/.cache/jerboa/positions.v1.json")
    )
    ap.add_argument(
        "--out", default=os.path.expanduser("~/.cache/jerboa/recommendations.v1.json")
    )
    ap.add_argument(
        "--sectors",
        nargs="*",
        default=None,
        help="Optional sector list (defaults to scoring engine defaults)",
    )
    ap.add_argument("--period", default="6mo")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--min-improvement", type=float, default=0.12)
    ap.add_argument("--max-swaps-per-day", type=int, default=1)
    ap.add_argument("--sector-cap", type=int, default=None)
    ap.add_argument("--turnover-cap", type=float, default=None)
    ap.add_argument("--quiet", action="store_true")

    args = ap.parse_args()

    pos_p = Path(args.positions)
    out_p = Path(args.out)

    positions = read_json(pos_p) if pos_p.exists() else {"positions": []}

    # Prefer cached sector rows if present (keeps exporter fast/offline-friendly on Jerboa).
    sect_cache = Path(os.path.expanduser("~/.cache/jerboa/market_health.sectors.json"))
    score_rows: List[Dict[str, Any]]
    used_source = "compute_scores"
    if sect_cache.exists():
        try:
            obj = json.loads(sect_cache.read_text(encoding="utf-8"))
            if isinstance(obj, list):
                score_rows = obj
                used_source = "market_health.sectors.json"
            elif isinstance(obj, dict):
                # allow a few common shapes
                for key in ("rows", "sectors", "data"):
                    v = obj.get(key)
                    if isinstance(v, list):
                        score_rows = v
                        used_source = f"market_health.sectors.json:{key}"
                        break
                else:
                    raise ValueError("no usable list in sectors cache")
            else:
                raise ValueError("unexpected sectors cache type")
        except Exception:
            # Fallback to compute_scores if cache unreadable
            score_rows = compute_scores(
                sectors=args.sectors, period=args.period, interval=args.interval
            )
    else:
        score_rows = compute_scores(
            sectors=args.sectors, period=args.period, interval=args.interval
        )

    # Stable asof: derived from input mtimes (so idempotency works).
    def mtime(p: Path) -> int:
        try:
            return int(p.stat().st_mtime)
        except Exception:
            return 0

    snap_epoch = max(mtime(pos_p), mtime(sect_cache))
    snap_iso = (
        datetime.fromtimestamp(snap_epoch, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
        if snap_epoch > 0
        else utc_now_iso()
    )

    score_rows: List[Dict[str, Any]] = compute_scores(
        sectors=args.sectors,
        period=args.period,
        interval=args.interval,
    )

    today, swaps_today, state_p = _load_swaps_today()

    rec = recommend(
        positions=positions,
        scores=score_rows,
        constraints={
            "min_improvement_threshold": args.min_improvement,
            "horizon_trading_days": args.horizon,
            "max_swaps_per_day": args.max_swaps_per_day,
            "swaps_today": swaps_today,
            "sector_cap": args.sector_cap,
            "turnover_cap": args.turnover_cap,
        },
    )

    # Always compute a trading-day target date (M9.6)

    horizon_days = int(getattr(args, "horizon", None) or 5)

    if "snap_iso" not in locals():
        snap_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    asof_date = datetime.fromisoformat(snap_iso.replace("Z", "+00:00")).date()

    target_trade_date = add_trading_days(asof_date, horizon_days).isoformat()

    doc: Dict[str, Any] = {
        "schema": "recommendations.v1",
        "asof": snap_iso,
        "generated_at": snap_iso,
        "inputs": {
            "positions_path": str(pos_p),
            "scores_source": used_source,
            "snapshot_epoch": snap_epoch,
            "period": args.period,
            "interval": args.interval,
            "horizon_trading_days": args.horizon,
            "min_improvement_threshold": args.min_improvement,
        },
        "recommendation": {
            "action": rec.action,
            "reason": rec.reason,
            "horizon_trading_days": rec.horizon_trading_days,
            "target_trade_date": target_trade_date,
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
        print(
            f"OK: wrote recommendations.v1 -> {out_p} (changed={changed}) action={rec.action}"
        )

    # M9 ledger: append a recommendation event (best-effort; must not break export)
    try:
        if "doc" in locals():
            from pathlib import Path as _Path

            ledger_db = (
                _Path(getattr(args, "out", "recommendations.v1.json")).resolve().parent
                / "ledger.v0.sqlite"
            )
            ts = doc.get("asof") or doc.get("generated_at")
            append_event(
                db_path=ledger_db,
                event_type="recommendation.v1",
                payload=doc,
                ts_utc=ts if isinstance(ts, str) else None,
            )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
