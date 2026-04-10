from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

from market_health.engine import compute_scores

CACHE_DIR = Path(os.path.expanduser("~/.cache/jerboa"))
REC_PATH = CACHE_DIR / "recommendations.v1.json"
FS_PATH = CACHE_DIR / "forecast_scores.v1.json"
POS_PATH = CACHE_DIR / "positions.v1.json"
UI_PATH = CACHE_DIR / "market_health.ui.v1.json"

SYM_KEYS = (
    "sym", "symbol", "candidate", "ticker", "to", "to_sym", "to_symbol",
    "target", "target_sym", "held", "from", "from_sym", "from_symbol",
)

NUM_KEYS_C = ("c", "C", "current", "score_c", "current_score")
NUM_KEYS_H1 = ("h1", "H1", "score_h1", "forecast_h1")
NUM_KEYS_H5 = ("h5", "H5", "score_h5", "forecast_h5")
NUM_KEYS_BLEND = ("blend", "Blend", "score", "utility", "blended", "blend_score")
NUM_KEYS_DELTA = ("delta", "ΔBlend", "dblend", "delta_blend")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _mtime_iso(path: Path) -> str | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat()
    except Exception:
        return None


def _pick_ts(doc: dict[str, Any], path: Path, keys: list[str]) -> str | None:
    for bucket in (doc, doc.get("meta"), doc.get("source_ts"), doc.get("summary"), doc.get("diagnostic")):
        if isinstance(bucket, dict):
            for key in keys:
                v = bucket.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return _mtime_iso(path)


def _digit(chk: Any) -> int:
    if isinstance(chk, dict) and isinstance(chk.get("score"), (int, float)):
        return max(0, min(2, int(chk["score"])))
    return 0


def _payload_fraction(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    cats = payload.get("categories")
    if not isinstance(cats, dict):
        return None
    pts = 0
    mx = 0
    for factor in ("A", "B", "C", "D", "E"):
        node = cats.get(factor)
        if not isinstance(node, dict):
            continue
        checks = node.get("checks")
        if not isinstance(checks, list):
            continue
        for chk in checks:
            pts += _digit(chk)
            mx += 2
    if not mx:
        return None
    return round(pts / mx, 2)


def _forecast_lookup(fs_doc: dict[str, Any]) -> dict[str, tuple[float | None, float | None]]:
    horizons = fs_doc.get("horizons_trading_days")
    if isinstance(horizons, list) and len(horizons) >= 2:
        try:
            h1d = int(horizons[0])
            h5d = int(horizons[1])
        except Exception:
            h1d, h5d = 1, 5
    else:
        h1d, h5d = 1, 5

    scores = fs_doc.get("scores")
    if not isinstance(scores, dict):
        return {}

    out: dict[str, tuple[float | None, float | None]] = {}
    for sym, by_h in scores.items():
        if not isinstance(sym, str) or not isinstance(by_h, dict):
            continue
        p1 = by_h.get(str(h1d), by_h.get(h1d))
        p5 = by_h.get(str(h5d), by_h.get(h5d))
        out[sym.strip().upper()] = (_payload_fraction(p1), _payload_fraction(p5))
    return out


def _extract_positions_symbols(pos_doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    rows = pos_doc.get("positions")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _looks_like_symbol(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{1,9}", s.strip()))


def _symbol_from_obj(obj: dict[str, Any]) -> str | None:
    for key in SYM_KEYS:
        v = obj.get(key)
        if isinstance(v, str):
            vv = v.strip().upper()
            if _looks_like_symbol(vv):
                return vv
    return None


def _parse_symbol_from_text(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    m = re.match(r"\s*([A-Z][A-Z0-9.\-]{1,9})\b", text.strip())
    return m.group(1) if m else None


def _collect_symbols(obj: Any, out: set[str]) -> None:
    if isinstance(obj, dict):
        sym = _symbol_from_obj(obj)
        if sym:
            out.add(sym)
        for k, v in obj.items():
            if k.lower() in {"best", "weakest"}:
                sym2 = _parse_symbol_from_text(v)
                if sym2:
                    out.add(sym2)
            _collect_symbols(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_symbols(v, out)


def _current_lookup(symbols: list[str]) -> dict[str, float | None]:
    syms = []
    seen = set()
    for s in symbols:
        ss = str(s or "").strip().upper()
        if ss and ss not in seen:
            seen.add(ss)
            syms.append(ss)

    if not syms:
        return {}

    try:
        rows = compute_scores(sectors=list(dict.fromkeys(["SPY", *syms])), period="6mo", interval="1d")
    except Exception:
        rows = []

    out: dict[str, float | None] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if sym:
            out[sym] = _payload_fraction(row)
    return out


def _blend(c: float | None, h1: float | None, h5: float | None) -> float | None:
    if c is None or h1 is None or h5 is None:
        return None
    return round((0.50 * c) + (0.25 * h1) + (0.25 * h5), 2)


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def _fmt_summary(sym: str, live: dict[str, tuple[float | None, float | None, float | None, float | None]]) -> str:
    c, h1, h5, b = live.get(sym, (None, None, None, None))
    return f"{sym}  (blend {_fmt(b)} | C {_fmt(c)} | H1 {_fmt(h1)} | H5 {_fmt(h5)})"


def _has_any_key(d: dict[str, Any], keys: tuple[str, ...]) -> bool:
    lowered = {k.lower() for k in d.keys()}
    return any(k.lower() in lowered for k in keys)


def _set_matching_keys(d: dict[str, Any], keys: tuple[str, ...], value: Any) -> None:
    keymap = {k.lower(): k for k in d.keys()}
    for k in keys:
        kk = keymap.get(k.lower())
        if kk is not None:
            d[kk] = value


def _patch_rows(obj: Any, live: dict[str, tuple[float | None, float | None, float | None, float | None]]) -> None:
    if isinstance(obj, dict):
        sym = _symbol_from_obj(obj)
        if sym and sym in live:
            c, h1, h5, b = live[sym]
            if _has_any_key(obj, NUM_KEYS_C):
                _set_matching_keys(obj, NUM_KEYS_C, c)
            if _has_any_key(obj, NUM_KEYS_H1):
                _set_matching_keys(obj, NUM_KEYS_H1, h1)
            if _has_any_key(obj, NUM_KEYS_H5):
                _set_matching_keys(obj, NUM_KEYS_H5, h5)
            if _has_any_key(obj, NUM_KEYS_BLEND):
                _set_matching_keys(obj, NUM_KEYS_BLEND, b)
        for v in obj.values():
            _patch_rows(v, live)
    elif isinstance(obj, list):
        for v in obj:
            _patch_rows(v, live)


def _find_candidate_rows(obj: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        sym = _symbol_from_obj(obj)
        if sym and (
            _has_any_key(obj, NUM_KEYS_BLEND)
            or _has_any_key(obj, NUM_KEYS_C)
            or _has_any_key(obj, NUM_KEYS_H1)
            or _has_any_key(obj, NUM_KEYS_H5)
        ):
            out.append(obj)
        for v in obj.values():
            _find_candidate_rows(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _find_candidate_rows(v, out)


def _sort_candidate_lists(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                if any(_symbol_from_obj(x) for x in v):
                    def keyfn(x: dict[str, Any]) -> tuple[float, float]:
                        try:
                            b = float(next((x[k] for k in x if k.lower() in {a.lower() for a in NUM_KEYS_BLEND}), -999.0))
                        except Exception:
                            b = -999.0
                        try:
                            d = float(next((x[k] for k in x if k.lower() in {a.lower() for a in NUM_KEYS_DELTA}), -999.0))
                        except Exception:
                            d = -999.0
                        return (b, d)
                    obj[k] = sorted(v, key=keyfn, reverse=True)
            _sort_candidate_lists(v)
    elif isinstance(obj, list):
        for v in obj:
            _sort_candidate_lists(v)


def _patch_timestamps_everywhere(obj: Any, forecast_asof: str | None, positions_asof: str | None, sectors_asof: str | None) -> None:
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            kl = k.lower()
            if "forecast" in kl and kl.endswith(("asof", "generated_at", "computed_at", "created_at", "source_asof")) and forecast_asof:
                obj[k] = forecast_asof
            elif "position" in kl and kl.endswith(("asof", "generated_at", "computed_at", "created_at", "source_asof")) and positions_asof:
                obj[k] = positions_asof
            elif ("sector" in kl or "snapshot" in kl) and kl.endswith(("asof", "generated_at", "computed_at", "created_at", "source_asof")) and sectors_asof:
                obj[k] = sectors_asof
        for v in obj.values():
            _patch_timestamps_everywhere(v, forecast_asof, positions_asof, sectors_asof)
    elif isinstance(obj, list):
        for v in obj:
            _patch_timestamps_everywhere(v, forecast_asof, positions_asof, sectors_asof)


def _patch_best_weakest_everywhere(obj: Any, best_text: str, weakest_text: str, delta: float | None) -> None:
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            kl = k.lower()
            if kl == "best":
                obj[k] = best_text
            elif kl == "weakest":
                obj[k] = weakest_text
            elif kl in {"delta", "Δblend".lower(), "dblend", "delta_blend"} and delta is not None:
                obj[k] = delta
        for v in obj.values():
            _patch_best_weakest_everywhere(v, best_text, weakest_text, delta)
    elif isinstance(obj, list):
        for v in obj:
            _patch_best_weakest_everywhere(v, best_text, weakest_text, delta)


def main() -> int:
    rec = _read_json(REC_PATH)
    fs = _read_json(FS_PATH)
    pos = _read_json(POS_PATH)
    ui = _read_json(UI_PATH)

    if not isinstance(rec, dict):
        raise SystemExit(f"ERR: could not read {REC_PATH}")

    forecast_asof = _pick_ts(fs, FS_PATH, ["forecast_asof", "asof", "generated_at", "computed_at", "created_at"])
    positions_asof = _pick_ts(pos, POS_PATH, ["positions_asof", "asof", "generated_at", "computed_at", "created_at"])
    sectors_asof = _pick_ts(ui, UI_PATH, ["sectors_asof", "snapshot_asof", "asof", "generated_at", "computed_at", "created_at"])

    held = _extract_positions_symbols(pos)

    syms: set[str] = set(held)
    _collect_symbols(rec, syms)
    all_syms = sorted(syms)

    c_lookup = _current_lookup(all_syms)
    fh_lookup = _forecast_lookup(fs)

    live: dict[str, tuple[float | None, float | None, float | None, float | None]] = {}
    for sym in all_syms:
        c = c_lookup.get(sym)
        h1, h5 = fh_lookup.get(sym, (None, None))
        live[sym] = (c, h1, h5, _blend(c, h1, h5))

    _patch_rows(rec, live)
    _sort_candidate_lists(rec)

    rows: list[dict[str, Any]] = []
    _find_candidate_rows(rec, rows)

    scored_rows = []
    for row in rows:
        sym = _symbol_from_obj(row)
        if not sym or sym not in live:
            continue
        c, h1, h5, b = live[sym]
        if b is None:
            continue
        scored_rows.append((sym, c, h1, h5, b))

    scored_rows.sort(key=lambda x: x[4], reverse=True)

    if scored_rows:
        best_sym = scored_rows[0][0]
        weakest_sym = scored_rows[-1][0]
        best_text = _fmt_summary(best_sym, live)
        weakest_text = _fmt_summary(weakest_sym, live)
        delta = round(scored_rows[0][4] - scored_rows[-1][4], 2)
        _patch_best_weakest_everywhere(rec, best_text, weakest_text, delta)

    _patch_timestamps_everywhere(rec, forecast_asof, positions_asof, sectors_asof)

    _write_json(REC_PATH, rec)
    print(f"OK: aggressively repaired recommendation payload -> {REC_PATH}")
    print(f"forecast_asof={forecast_asof}")
    print(f"positions_asof={positions_asof}")
    print(f"sectors_asof={sectors_asof}")
    print(f"held_symbols={held}")
    print(f"live_symbols={len(live)}")
    print(f"scored_candidate_rows={len(scored_rows)}")


if __name__ == "__main__":
    raise SystemExit(main())
