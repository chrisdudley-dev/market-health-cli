#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe

Number = Union[int, float]


def utc_iso_from_epoch(epoch: int) -> str:
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _read_json(p: Path) -> Optional[Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _as_num_list(x: Any) -> Optional[List[float]]:
    if isinstance(x, list) and x and all(isinstance(v, (int, float)) for v in x):
        return [float(v) for v in x]
    return None


def _extract_symbol_block(obj: Any) -> Optional[OHLCV]:
    """
    Accepts dict formats like:
      {close:[...], high:[...], low:[...], volume:[...]}
      {close_series:[...], high_series:[...], low_series:[...], volume_series:[...]}
      {prices:[...]}  (close only)
    """
    if not isinstance(obj, dict):
        return None

    close = (
        _as_num_list(obj.get("close"))
        or _as_num_list(obj.get("close_series"))
        or _as_num_list(obj.get("prices"))
    )
    if not close:
        return None

    high = _as_num_list(obj.get("high")) or _as_num_list(obj.get("high_series"))
    low = _as_num_list(obj.get("low")) or _as_num_list(obj.get("low_series"))
    volume = (
        _as_num_list(obj.get("volume"))
        or _as_num_list(obj.get("vol"))
        or _as_num_list(obj.get("volume_series"))
    )
    return OHLCV(close=close, high=high, low=low, volume=volume)


def _extract_from_symbol_map(obj: Any) -> Dict[str, OHLCV]:
    out: Dict[str, OHLCV] = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        if not isinstance(k, str) or not k.strip():
            continue
        blk = _extract_symbol_block(v)
        if blk:
            out[k.strip().upper()] = blk
    return out


def _extract_from_rows(obj: Any) -> Dict[str, OHLCV]:
    """
    Accept list[{symbol, ...series...}] or dict with a list under rows/sectors/data.sectors.
    """
    rows: Optional[List[Any]] = None
    if isinstance(obj, list):
        rows = obj
    elif isinstance(obj, dict):
        for key in ("rows", "sectors"):
            v = obj.get(key)
            if isinstance(v, list):
                rows = v
                break
        if rows is None:
            data = obj.get("data")
            if isinstance(data, dict) and isinstance(data.get("sectors"), list):
                rows = data["sectors"]

    if not isinstance(rows, list):
        return {}

    out: Dict[str, OHLCV] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = row.get("symbol") or row.get("ticker") or row.get("id")
        if not isinstance(sym, str) or not sym.strip():
            continue
        blk = _extract_symbol_block(row)
        if blk:
            out[sym.strip().upper()] = blk
    return out


def _maybe_has_close_array(p: Path) -> bool:
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return bool(re.search(r'"close(_series)?"\s*:\s*\[', txt))


def discover_ohlcv(
    cache_dir: Path,
) -> Tuple[Dict[str, OHLCV], Optional[str], List[str]]:
    sources: List[str] = []
    best: Dict[str, OHLCV] = {}
    best_asof: Optional[str] = None

    candidates = sorted(
        cache_dir.glob("*.json"), key=lambda q: q.stat().st_mtime, reverse=True
    )
    for p in candidates:
        if not _maybe_has_close_array(p):
            continue
        obj = _read_json(p)
        if obj is None:
            continue

        extracted = _extract_from_symbol_map(obj)
        if not extracted:
            extracted = _extract_from_rows(obj)
        if not extracted:
            continue

        sources.append(str(p))

        asof = None
        if isinstance(obj, dict):
            asof = obj.get("asof") or obj.get("generated_at") or obj.get("timestamp")
        if not isinstance(asof, str) or not asof:
            asof = utc_iso_from_epoch(int(p.stat().st_mtime))

        for sym, blk in extracted.items():
            if sym not in best:
                best[sym] = blk

        if best_asof is None:
            best_asof = asof

        if "SPY" in best and len(best) >= 8:
            break

    return best, best_asof, sources


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        old_text = path.read_text(encoding="utf-8", errors="replace")
        if old_text == new_text:
            return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)
    return True


def _parse_horizons(s: str) -> List[int]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out: List[int] = []
    for p in parts:
        if not p.isdigit():
            continue
        out.append(int(p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export forecast_scores.v1.json to ~/.cache/jerboa/"
    )
    ap.add_argument(
        "--out", default=os.path.expanduser("~/.cache/jerboa/forecast_scores.v1.json")
    )
    ap.add_argument("--cache-dir", default=os.path.expanduser("~/.cache/jerboa"))
    ap.add_argument(
        "--source",
        default=None,
        help="Optional JSON source containing SPY + sector OHLCV arrays",
    )
    ap.add_argument(
        "--horizons", default="1,5", help="Comma-separated horizons in trading days"
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out_p = Path(args.out)
    cache_dir = Path(args.cache_dir)

    # Issue #121: load upstream provider caches (no network I/O in scoring)
    flow_by_symbol = {}
    flow_meta = {"path": str(cache_dir / "flow.v1.json"), "status": "missing"}
    try:
        fp = cache_dir / "flow.v1.json"
        if fp.exists():
            obj = _read_json(fp)
            flow_meta["status"] = str(obj.get("status") or "")
            flow_meta["generated_at"] = obj.get("generated_at")
            flow_meta["source"] = obj.get("source")
            pts = obj.get("points") or []
            if isinstance(pts, list):
                for row in pts:
                    if (
                        isinstance(row, dict)
                        and isinstance(row.get("symbol"), str)
                        and isinstance(row.get("metrics"), dict)
                    ):
                        sym = row["symbol"].strip().upper()
                        flow_by_symbol[sym] = {
                            str(k): float(v)
                            for k, v in row["metrics"].items()
                            if isinstance(v, (int, float))
                        }
            flow_meta["points"] = len(flow_by_symbol)
    except Exception as e:
        flow_meta["status"] = "error"
        flow_meta["error"] = str(e)

    iv_by_symbol = {}
    iv_meta = {"path": str(cache_dir / "iv.v1.json"), "status": "missing"}
    try:
        ip = cache_dir / "iv.v1.json"
        if ip.exists():
            obj = _read_json(ip)
            iv_meta["status"] = str(obj.get("status") or "")
            iv_meta["generated_at"] = obj.get("generated_at")
            iv_meta["source"] = obj.get("source")
            pts = obj.get("points") or []
            if isinstance(pts, list):
                for row in pts:
                    if isinstance(row, dict) and isinstance(row.get("symbol"), str):
                        sym = row["symbol"].strip().upper()
                        iv_by_symbol[sym] = {
                            "iv": float(row.get("iv") or 0.0),
                            "iv_rank_1y": float(row.get("iv_rank_1y") or 0.0),
                            "iv_percentile_1y": float(
                                row.get("iv_percentile_1y") or 0.0
                            ),
                        }
            iv_meta["points"] = len(iv_by_symbol)
    except Exception as e:
        iv_meta["status"] = "error"
        iv_meta["error"] = str(e)

    horizons = _parse_horizons(str(args.horizons))
    if not horizons:
        horizons = [1, 5]

    sources: List[str] = []
    asof: Optional[str] = None
    ohlcv_map: Dict[str, OHLCV] = {}

    if args.source:
        src = Path(os.path.expanduser(str(args.source)))
        obj = _read_json(src)
        if obj is not None:
            ohlcv_map = _extract_from_symbol_map(obj)
            if not ohlcv_map:
                ohlcv_map = _extract_from_rows(obj)
            if isinstance(obj, dict):
                asof = (
                    obj.get("asof") or obj.get("generated_at") or obj.get("timestamp")
                )
            if not isinstance(asof, str) or not asof:
                try:
                    asof = utc_iso_from_epoch(int(src.stat().st_mtime))
                except Exception:
                    asof = None
            sources = [str(src)]

    if not ohlcv_map:
        ohlcv_map, asof, sources = discover_ohlcv(cache_dir)

    if not isinstance(asof, str) or not asof:
        try:
            asof = utc_iso_from_epoch(int(out_p.parent.stat().st_mtime))
        except Exception:
            asof = utc_iso_from_epoch(int(datetime.now(tz=timezone.utc).timestamp()))

    spy = ohlcv_map.get("SPY")
    if spy is None:
        if not args.quiet:
            print(
                f"ERR: could not discover SPY OHLCV in {cache_dir}. "
                "Provide --source with SPY close/high/low/volume arrays."
            )
            return 2

    universe = {k: v for k, v in ohlcv_map.items() if k != "SPY"}

    scores = compute_forecast_universe(
        universe=universe,
        spy=spy,
        horizons_trading_days=tuple(horizons),
        flow_by_symbol=flow_by_symbol,
        flow_status=flow_meta.get("status"),
        iv_by_symbol=iv_by_symbol,
        iv_status=iv_meta.get("status"),
    )

    doc: Dict[str, Any] = {
        "schema": "forecast_scores.v1",
        "asof": asof,
        "horizons_trading_days": horizons,
        "scores": scores,
        "inputs": {
            "sources": sources,
            "cache_dir": str(cache_dir),
            "symbols": len(scores),
        },
    }

    # Issue #121: record provider cache metadata for auditability

    doc.setdefault("inputs", {})

    doc["inputs"]["flow"] = flow_meta

    doc["inputs"]["iv"] = iv_meta

    changed = atomic_write_json(out_p, doc)
    if not args.quiet:
        print(
            f"OK: wrote {out_p} changed={changed} symbols={len(scores)} horizons={horizons}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
