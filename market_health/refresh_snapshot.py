from __future__ import annotations

import json
import os
import subprocess
import sys
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_repo_script(script_rel: str) -> None:
    script = _repo_root() / script_rel
    if not script.exists():
        return

    env = dict(os.environ)
    root = str(_repo_root())
    env["PYTHONPATH"] = root if not env.get("PYTHONPATH") else root + os.pathsep + env["PYTHONPATH"]

    subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_repo_root()),
        env=env,
        check=False,
    )


def _ensure_refresh_inputs() -> None:
    _run_repo_script("scripts/export_forecast_scores_v1.py")
    _run_repo_script("scripts/backfill_forecast_scores_from_positions.py")
    _run_repo_script("scripts/export_recommendations_v1.py")

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


def _load_etf_symbols() -> List[str]:
    out: List[str] = []
    try:
        from market_health.etf_universe_v1 import load_etf_universe
    except Exception:
        return out

    try:
        rows = load_etf_universe()
    except Exception:
        rows = []

    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                sym = row.get("symbol")
                if isinstance(sym, str):
                    out.append(sym.upper().strip())
            elif isinstance(row, str):
                out.append(row.upper().strip())

    seen = set()
    uniq: List[str] = []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq




def _rows_by_symbol(rows):
    out = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sym = row.get("symbol")
        if not isinstance(sym, str) or not sym.strip():
            continue
        out[sym.strip().upper()] = row
    return out


def _held_symbols(pos_doc):
    out = []
    seen = set()
    for pos in (pos_doc.get("positions") or []) if isinstance(pos_doc, dict) else []:
        if not isinstance(pos, dict):
            continue
        sym = pos.get("symbol") or pos.get("ticker")
        if not isinstance(sym, str) or not sym.strip():
            continue
        ss = sym.strip().upper()
        if ss not in seen:
            seen.add(ss)
            out.append(ss)
    return out


def _candidate_symbols(rec_doc):
    out = []
    seen = set()
    rows = []
    if isinstance(rec_doc, dict):
        rows = rec_doc.get("candidate_rows") or []
        if not rows and isinstance(rec_doc.get("diagnostic"), dict):
            rows = rec_doc["diagnostic"].get("candidate_rows") or []
        if not rows and isinstance(rec_doc.get("diagnostics"), dict):
            rows = rec_doc["diagnostics"].get("candidate_rows") or []
        if not rows and isinstance(rec_doc.get("recommendation"), dict):
            rec = rec_doc["recommendation"]
            if isinstance(rec.get("diagnostics"), dict):
                rows = rec["diagnostics"].get("candidate_rows") or []
            elif isinstance(rec.get("diagnostic"), dict):
                rows = rec["diagnostic"].get("candidate_rows") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = row.get("sym") or row.get("symbol") or row.get("candidate")
        if not isinstance(sym, str) or not sym.strip():
            continue
        ss = sym.strip().upper()
        if ss not in seen:
            seen.add(ss)
            out.append(ss)
    return out


def _pair_symbols(rec_doc):
    from_syms, to_syms = [], []
    seen_from, seen_to = set(), set()
    rows = []
    if isinstance(rec_doc, dict):
        rows = rec_doc.get("candidate_pairs") or []
        if not rows and isinstance(rec_doc.get("diagnostic"), dict):
            rows = rec_doc["diagnostic"].get("candidate_pairs") or []
        if not rows and isinstance(rec_doc.get("diagnostics"), dict):
            rows = rec_doc["diagnostics"].get("candidate_pairs") or []
        if not rows and isinstance(rec_doc.get("recommendation"), dict):
            rec = rec_doc["recommendation"]
            if isinstance(rec.get("diagnostics"), dict):
                rows = rec["diagnostics"].get("candidate_pairs") or []
            elif isinstance(rec.get("diagnostic"), dict):
                rows = rec["diagnostic"].get("candidate_pairs") or []

    for row in rows:
        if not isinstance(row, dict):
            continue
        fs = row.get("from_symbol")
        ts = row.get("to_symbol")
        if isinstance(fs, str) and fs.strip():
            ss = fs.strip().upper()
            if ss not in seen_from:
                seen_from.add(ss)
                from_syms.append(ss)
        if isinstance(ts, str) and ts.strip():
            ss = ts.strip().upper()
            if ss not in seen_to:
                seen_to.add(ss)
                to_syms.append(ss)

    return {"from": from_syms, "to": to_syms}


def build_snapshot(
    period: str = "6mo",
    interval: str = "1d",
    ttl: int = 900,
    include_inverses: bool = True,
) -> dict:
    sectors = [s.upper().strip() for s in (SECTORS_DEFAULT or [])]
    sectors = sectors + _load_etf_symbols()
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
    _ensure_refresh_inputs()
    pos_doc = _read_json(POS_PATH)
    rec_doc = _read_json(REC_PATH)
    fs_doc = _read_json(FS_PATH)

    rows_by_symbol = _rows_by_symbol(rows if isinstance(rows, list) else [])
    held_symbols = _held_symbols(pos_doc if isinstance(pos_doc, dict) else {})
    forecast_candidate_symbols = _candidate_symbols(rec_doc if isinstance(rec_doc, dict) else {})
    pair_symbols = _pair_symbols(rec_doc if isinstance(rec_doc, dict) else {})

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
"state": {
    "universes": {
        "all": list(rows_by_symbol.keys()),
        "held": held_symbols,
        "forecast_candidates": forecast_candidate_symbols,
        "forecast_pair_from": pair_symbols["from"],
        "forecast_pair_to": pair_symbols["to"],
    },
    "rows_by_symbol": rows_by_symbol,
},
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
