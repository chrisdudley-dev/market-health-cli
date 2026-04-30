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
from market_health.universe import INVERSE_SYMBOLS, get_default_scoring_symbols

try:
    import yfinance as yf
except Exception:
    yf = None

Number = Union[int, float]


def utc_iso_from_epoch(epoch: int) -> str:
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _mtime_epoch(p: Path) -> Optional[int]:
    try:
        return int(p.stat().st_mtime)
    except Exception:
        return None


def _is_path_fresh(p: Path, *, max_age_seconds: int) -> bool:
    if max_age_seconds <= 0:
        return True
    ts = _mtime_epoch(p)
    if ts is None:
        return False
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    return (now_ts - ts) <= max_age_seconds


def _parse_iso_utc(s: Optional[str]) -> Optional[datetime]:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _max_iso(a: Optional[str], b: Optional[str]) -> Optional[str]:
    da = _parse_iso_utc(a)
    db = _parse_iso_utc(b)
    if da is None:
        return b if db is not None else None
    if db is None:
        return a
    return a if da >= db else b


def _latest_source_file_asof(paths: List[str], current: Optional[str]) -> Optional[str]:
    best = current
    for raw in paths or []:
        try:
            mtime_iso = utc_iso_from_epoch(int(Path(raw).stat().st_mtime))
        except Exception:
            continue
        best = _max_iso(best, mtime_iso) or best or mtime_iso
    return best


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
    target_symbols: Optional[set[str]] = None,
    max_source_age_seconds: int = 0,
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
        if max_source_age_seconds > 0 and not _is_path_fresh(
            p, max_age_seconds=max_source_age_seconds
        ):
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

        file_asof = utc_iso_from_epoch(int(p.stat().st_mtime))
        asof = None
        if isinstance(obj, dict):
            asof = obj.get("asof") or obj.get("generated_at") or obj.get("timestamp")
        asof = _max_iso(asof, file_asof) or file_asof

        for sym, blk in extracted.items():
            if sym not in best:
                best[sym] = blk

        best_asof = _max_iso(best_asof, asof) or asof

        if target_symbols:
            if target_symbols.issubset(set(best.keys())):
                break
        elif "SPY" in best and len(best) >= 8:
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


def _download_missing_ohlcv(
    symbols: List[str],
    period: str = "6mo",
    interval: str = "1d",
) -> Dict[str, OHLCV]:
    out: Dict[str, OHLCV] = {}
    if not symbols:
        return out

    if yf is None:
        return {}

    data = yf.download(
        tickers=symbols,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="ticker",
    )

    if data is None:
        return out

    if getattr(data.columns, "nlevels", 1) > 1:
        for sym in symbols:
            sym_u = sym.strip().upper()
            try:
                frame = data[sym_u]
            except Exception:
                continue

            def _vals(col: str) -> Optional[List[float]]:
                if col not in frame:
                    return None
                vals = [float(v) for v in frame[col].tolist() if v == v]
                return vals or None

            close = _vals("Close")
            if not close:
                continue

            out[sym_u] = OHLCV(
                close=close,
                high=_vals("High"),
                low=_vals("Low"),
                volume=_vals("Volume"),
            )
        return out

    sym_u = symbols[0].strip().upper()

    def _vals_single(col: str) -> Optional[List[float]]:
        if col not in data:
            return None
        vals = [float(v) for v in data[col].tolist() if v == v]
        return vals or None

    close = _vals_single("Close")
    if close:
        out[sym_u] = OHLCV(
            close=close,
            high=_vals_single("High"),
            low=_vals_single("Low"),
            volume=_vals_single("Volume"),
        )

    return out


def _tail_trim(xs: Optional[List[float]], n: int) -> Optional[List[float]]:
    if xs is None:
        return None
    if n <= 0:
        return None
    if len(xs) < n:
        return None
    return [float(v) for v in xs[-n:]]


def _trim_ohlcv(ohlcv: OHLCV, n: int) -> Optional[OHLCV]:
    close = _tail_trim(ohlcv.close, n)
    if not close:
        return None
    high = _tail_trim(ohlcv.high, n) if ohlcv.high is not None else None
    low = _tail_trim(ohlcv.low, n) if ohlcv.low is not None else None
    volume = _tail_trim(ohlcv.volume, n) if ohlcv.volume is not None else None
    return OHLCV(close=close, high=high, low=low, volume=volume)


def _align_universe_lengths(
    spy: OHLCV, universe: Dict[str, OHLCV]
) -> Tuple[OHLCV, Dict[str, OHLCV]]:
    lengths = [len(spy.close)]
    for o in universe.values():
        if getattr(o, "close", None):
            lengths.append(len(o.close))
    n = min(x for x in lengths if x > 0)

    spy2 = _trim_ohlcv(spy, n)
    if spy2 is None:
        raise ValueError("could not align SPY series")

    out: Dict[str, OHLCV] = {}
    for sym, o in universe.items():
        o2 = _trim_ohlcv(o, n)
        if o2 is not None:
            out[sym] = o2
    return spy2, out


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    ap.add_argument(
        "--max-source-age-minutes",
        type=int,
        default=int(os.environ.get("JERBOA_FORECAST_MAX_SOURCE_AGE_MINUTES", "20")),
        help="Ignore cached OHLCV JSON sources older than this many minutes (0 disables the age check).",
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

    source_max_age_seconds = max(0, int(args.max_source_age_minutes or 0)) * 60

    sources: List[str] = []
    asof: Optional[str] = None
    ohlcv_map: Dict[str, OHLCV] = {}

    if args.source:
        src = Path(os.path.expanduser(str(args.source)))
        if src.exists() and _is_path_fresh(src, max_age_seconds=source_max_age_seconds):
            obj = _read_json(src)
            if obj is not None:
                ohlcv_map = _extract_from_symbol_map(obj)
                if not ohlcv_map:
                    ohlcv_map = _extract_from_rows(obj)
                if isinstance(obj, dict):
                    asof = (
                        obj.get("asof")
                        or obj.get("generated_at")
                        or obj.get("timestamp")
                    )
                try:
                    file_asof = utc_iso_from_epoch(int(src.stat().st_mtime))
                except Exception:
                    file_asof = None
                asof = _max_iso(asof, file_asof) or asof or file_asof
                sources = [str(src)]

    target_symbols = {"SPY", *get_default_scoring_symbols(), *INVERSE_SYMBOLS}

    if not ohlcv_map:
        ohlcv_map, asof, sources = discover_ohlcv(
            cache_dir,
            target_symbols=set(target_symbols),
            max_source_age_seconds=source_max_age_seconds,
        )

    missing_symbols = sorted(set(target_symbols) - set(ohlcv_map.keys()))
    if missing_symbols:
        downloaded = _download_missing_ohlcv(
            missing_symbols, period="6mo", interval="1d"
        )
        if downloaded:
            ohlcv_map.update(downloaded)
            sources.append("yfinance:" + ",".join(sorted(downloaded.keys())))

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
    if spy is None or getattr(spy, "close", None) is None:
        raise SystemExit("forecast refresh failed: missing SPY benchmark data")
    spy, universe = _align_universe_lengths(spy, universe)

    scores = compute_forecast_universe(
        universe=universe,
        spy=spy,
        horizons_trading_days=tuple(horizons),
        flow_by_symbol=flow_by_symbol,
        flow_status=flow_meta.get("status"),
        iv_by_symbol=iv_by_symbol,
        iv_status=iv_meta.get("status"),
    )

    export_now = utc_now_iso()

    doc: Dict[str, Any] = {
        "schema": "forecast_scores.v1",
        "snapshot_asof": export_now,
        "asof": export_now,
        "generated_at": export_now,
        "source_asof": _latest_source_file_asof(sources, asof),
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
