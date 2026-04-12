from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(os.path.expanduser("~/.cache/jerboa"))
POS_PATH = CACHE_DIR / "positions.v1.json"
FS_PATH = CACHE_DIR / "forecast_scores.v1.json"


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


def _extract_symbols_from_positions(doc: dict[str, Any]) -> list[str]:
    syms: list[str] = []

    v = doc.get("symbols") if isinstance(doc, dict) else None
    if isinstance(v, list):
        for x in v:
            if x is not None:
                syms.append(str(x).upper().strip())

    v = doc.get("positions") if isinstance(doc, dict) else None
    if isinstance(v, list):
        for row in v:
            if isinstance(row, dict):
                sym = row.get("symbol") or row.get("sym") or row.get("ticker")
                if sym:
                    syms.append(str(sym).upper().strip())

    seen: set[str] = set()
    out: list[str] = []
    for s in syms:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def main() -> int:
    pos_doc = _read_json(POS_PATH)
    fs_doc = _read_json(FS_PATH)

    held = _extract_symbols_from_positions(pos_doc) if isinstance(pos_doc, dict) else []
    seen: set[str] = set()
    held_syms: list[str] = []
    for sym in held:
        ss = str(sym or "").strip().upper()
        if ss and ss not in seen:
            seen.add(ss)
            held_syms.append(ss)

    if not held_syms:
        print("OK: no held symbols found; nothing to backfill")
        return 0

    before = json.dumps(fs_doc if isinstance(fs_doc, dict) else {}, sort_keys=True)

    try:
        from market_health.dashboard_legacy import _ensure_forecast_payloads  # type: ignore
    except Exception:
        _ensure_forecast_payloads = None

    if callable(_ensure_forecast_payloads):
        fs_doc = _ensure_forecast_payloads(
            fs_doc if isinstance(fs_doc, dict) else {},
            held_syms,
            period=os.environ.get("MH_PERIOD", "6mo"),
            interval=os.environ.get("MH_INTERVAL", "1d"),
            horizons=(1, 5),
        )
    else:
        fs_doc = fs_doc if isinstance(fs_doc, dict) else {}

    after = json.dumps(fs_doc, sort_keys=True)
    changed = before != after

    _write_json(FS_PATH, fs_doc)

    scores = fs_doc.get("scores") if isinstance(fs_doc, dict) else {}
    scores = scores if isinstance(scores, dict) else {}

    covered = [s for s in held_syms if isinstance(scores.get(s), dict)]
    missing = [s for s in held_syms if s not in covered]

    print(
        f"OK: backfilled held forecasts -> {FS_PATH} "
        f"changed={changed} covered={covered} missing={missing}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
