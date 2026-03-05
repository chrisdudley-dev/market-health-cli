from __future__ import annotations

import json
import os
import datetime as dt
from pathlib import Path
from typing import List

from market_health.engine import (
    compute_scores,
    SECTORS_DEFAULT,
)  # existing in your repo

CACHE_DIR = Path(os.path.expanduser("~/.cache/jerboa"))

UI_PATH = Path(
    os.environ.get("JERBOA_UI_JSON", str(CACHE_DIR / "market_health.ui.v1.json"))
).expanduser()
POS_PATH = CACHE_DIR / "positions.v1.json"
REC_PATH = CACHE_DIR / "recommendations.v1.json"
FS_PATH = CACHE_DIR / "forecast_scores.v1.json"
INV_PATH = CACHE_DIR / "inverse_universe.v1.json"


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _now_asof() -> str:
    # ISO8601 in UTC with offset
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _load_inverse_symbols() -> List[str]:
    inv = _read_json(INV_PATH)
    out: List[str] = []

    # inverse_universe.v1.json (your current shape): {"pairs":[{"long":"XLK","inverse":"TECS",...}, ...]}
    pairs = inv.get("pairs") if isinstance(inv, dict) else None
    if isinstance(pairs, list):
        for it in pairs:
            if isinstance(it, dict):
                v = it.get("inverse")
                if isinstance(v, str):
                    out.append(v.upper().strip())

    # tolerate older/alternate shapes too
    if isinstance(inv, list):
        for x in inv:
            if isinstance(x, str):
                out.append(x.upper().strip())
            elif isinstance(x, dict) and isinstance(x.get("symbol"), str):
                out.append(x["symbol"].upper().strip())
    elif isinstance(inv, dict):
        syms = inv.get("symbols")
        if isinstance(syms, list):
            for x in syms:
                if isinstance(x, str):
                    out.append(x.upper().strip())
        inv_map = inv.get("inverse_map")
        if isinstance(inv_map, dict):
            for k in inv_map.keys():
                if isinstance(k, str):
                    out.append(k.upper().strip())
            for v in inv_map.values():
                if isinstance(v, str):
                    out.append(v.upper().strip())

    # unique preserve order
    seen = set()

    uniq = []
    for s in out:
        if s and s not in seen:
            seen.add(s)

            uniq.append(s)
    return uniq


def build_snapshot(
    period: str = "6mo",
    interval: str = "1d",
    ttl: int = 900,
    include_inverses: bool = True,
) -> dict:
    sectors = [s.upper().strip() for s in (SECTORS_DEFAULT or [])]
    if include_inverses:
        sectors = sectors + _load_inverse_symbols()

    # unique preserve order
    seen = set()

    order = []
    for s in sectors:
        if s and s not in seen:
            seen.add(s)

            order.append(s)

    # --- compute current scoring payload ---
    # compute_scores returns list[dict] with shape expected by your UI
    rows = compute_scores(sectors=order, period=period, interval=interval)

    # --- load cached supporting docs (positions, reco, forecast) ---
    pos_doc = _read_json(POS_PATH)
    rec_doc = _read_json(REC_PATH)
    fs_doc = _read_json(FS_PATH)

    snap = {
        "schema": "market_health.ui.v1",
        "asof": _now_asof(),
        "meta": {
            "generator": "market_health.refresh_snapshot",
            "period": period,
            "interval": interval,
            "ttl": ttl,
            "include_inverses": include_inverses,
        },
        "data": {
            # keep dashboard + ui_triscore_ascii happy
            "sectors": rows if isinstance(rows, list) else [],
            "positions": pos_doc if isinstance(pos_doc, dict) else {},
            "recommendations": rec_doc if isinstance(rec_doc, dict) else {},
            "forecast_scores": fs_doc if isinstance(fs_doc, dict) else {},
            "state": {},
            "events": {},
            "environment": {},
        },
        "status_line": "snapshot",
        "summary": {},
    }
    return snap


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Build market_health.ui.v1.json snapshot (atomic)."
    )
    p.add_argument("--period", default=os.environ.get("MH_PERIOD", "6mo"))
    p.add_argument("--interval", default=os.environ.get("MH_INTERVAL", "1d"))
    p.add_argument("--ttl", type=int, default=int(os.environ.get("MH_TTL", "900")))
    p.add_argument("--no-inverses", action="store_true")
    p.add_argument("--out", default=str(UI_PATH))
    args = p.parse_args()

    out_p = Path(args.out).expanduser()
    snap = build_snapshot(
        period=str(args.period),
        interval=str(args.interval),
        ttl=int(args.ttl),
        include_inverses=not args.no_inverses,
    )
    _write_json_atomic(out_p, snap)
    print(f"[ok] wrote snapshot: {out_p}")
    print(f"[asof] {snap.get('asof')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
