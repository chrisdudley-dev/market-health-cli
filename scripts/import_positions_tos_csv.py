#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "positions.v1"

SEARCH_DIRS_DEFAULT = [
    "~/imports/thinkorswim",
    "~/imports/tos",
    "~/Downloads",
]

# --- parsing helpers ---

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()

def _try_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.replace(",", "")
    # allow parentheses negative like (123.45)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except Exception:
        return None

def _try_int(x: Any) -> Optional[int]:
    f = _try_float(x)
    if f is None:
        return None
    try:
        return int(round(f))
    except Exception:
        return None

def _sniff_dialect(path: Path) -> csv.Dialect:
    sample = path.read_text("utf-8", errors="replace")[:8192]
    sniffer = csv.Sniffer()
    try:
        return sniffer.sniff(sample, delimiters=[",", "\t", ";", "|"])
    except Exception:
        # default comma
        class D(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        return D

def _normalize_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())

def _pick_latest_csv(search_dirs: List[str]) -> Optional[Path]:
    candidates: List[Path] = []
    patterns = [
        re.compile(r".*pos.*\.csv$", re.I),
        re.compile(r".*position.*\.csv$", re.I),
        re.compile(r".*account.*\.csv$", re.I),
        re.compile(r".*statement.*\.csv$", re.I),
    ]
    for d in search_dirs:
        dd = _expand(d)
        if not dd.exists() or not dd.is_dir():
            continue
        for p in dd.glob("*.csv"):
            name = p.name
            if any(rx.match(name) for rx in patterns):
                candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)

# --- option descriptor parsing (best-effort) ---

# Common ToS-style: "SPY 02/14/2026 500 C"
_RX_TOS = re.compile(
    r"^(?P<under>[A-Z0-9.\-]+)\s+(?P<mm>\d{2})/(?P<dd>\d{2})/(?P<yyyy>\d{4})\s+(?P<strike>\d+(?:\.\d+)?)\s*(?P<right>[CP])\b"
)

# OCC-style: "SPY260214C00500000"
_RX_OCC = re.compile(
    r"^(?P<under>[A-Z0-9.\-]{1,6})(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<right>[CP])(?P<strike>\d{8})$"
)

def _parse_option(desc: str) -> Optional[Dict[str, Any]]:
    s = (desc or "").strip()
    if not s:
        return None

    m = _RX_TOS.match(s)
    if m:
        yyyy = int(m.group("yyyy"))
        mm = int(m.group("mm"))
        dd = int(m.group("dd"))
        expiry = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
        return {
            "underlying": m.group("under"),
            "expiry": expiry,
            "strike": float(m.group("strike")),
            "right": m.group("right"),
            "multiplier": 100,
        }

    m = _RX_OCC.match(s.replace(" ", ""))
    if m:
        under = m.group("under")
        yy = int(m.group("yy"))
        yyyy = 2000 + yy
        mm = int(m.group("mm"))
        dd = int(m.group("dd"))
        expiry = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
        strike = int(m.group("strike")) / 1000.0
        return {
            "underlying": under,
            "expiry": expiry,
            "strike": float(strike),
            "right": m.group("right"),
            "multiplier": 100,
        }

    return None

def _guess_symbol(row: Dict[str, str]) -> str:
    # Try several common headers
    for key in ("symbol", "ticker", "underlying"):
        for h, v in row.items():
            if _normalize_header(h) == key and str(v).strip():
                return str(v).strip().upper()
    # fallback: first non-empty token in Description
    desc = row.get("Description") or row.get("description") or ""
    tok = (desc.strip().split() or ["?"])[0]
    return tok.upper()

def _find_col(row: Dict[str, str], *names: str) -> Optional[str]:
    wanted = {n.lower() for n in names}
    for h in row.keys():
        if _normalize_header(h) in wanted:
            return h
    return None

def _parse_positions(csv_path: Path) -> List[Dict[str, Any]]:
    dialect = _sniff_dialect(csv_path)
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        rows = list(reader)

    out: List[Dict[str, Any]] = []
    for idx, r in enumerate(rows, start=1):
        # Skip blank rows
        if not any((v or "").strip() for v in r.values()):
            continue

        # Try to detect qty
        qty_col = _find_col(r, "qty", "quantity", "net qty", "net quantity", "position", "pos")
        qty = _try_int(r.get(qty_col, "")) if qty_col else None
        if qty is None:
            # some exports use "Long Quantity"/"Short Quantity"
            q1 = _try_int(r.get(_find_col(r, "long quantity") or "", ""))
            q2 = _try_int(r.get(_find_col(r, "short quantity") or "", ""))
            if q1 is not None:
                qty = q1
            elif q2 is not None:
                qty = -abs(q2)

        # If still no qty, ignore the row (often headers/notes)
        if qty is None or qty == 0:
            continue

        desc_col = _find_col(r, "description", "instrument", "symbol description", "security description")
        desc = (r.get(desc_col, "") if desc_col else "").strip()

        opt = _parse_option(desc)
        sym_col = _find_col(r, "symbol", "ticker")
        symbol = (r.get(sym_col, "") if sym_col else "").strip().upper()

        if opt:
            underlying = opt["underlying"].upper()
            rec = {
                "asset_type": "option",
                "symbol": underlying,
                "qty": qty,
                "option": opt,
                "avg_price": _try_float(r.get(_find_col(r, "average price", "avg price", "trade price") or "", "")),
                "mark": _try_float(r.get(_find_col(r, "mark", "last", "price") or "", "")),
                "market_value": _try_float(r.get(_find_col(r, "market value", "value") or "", "")),
                "source": {"file": str(csv_path), "row": idx, "description": desc},
            }
            out.append(rec)
            continue

        # Equity / ETF position
        if not symbol:
            symbol = _guess_symbol(r)

        rec = {
            "asset_type": "equity",
            "symbol": symbol,
            "qty": qty,
            "avg_price": _try_float(r.get(_find_col(r, "average price", "avg price", "trade price") or "", "")),
            "mark": _try_float(r.get(_find_col(r, "mark", "last", "price") or "", "")),
            "market_value": _try_float(r.get(_find_col(r, "market value", "value") or "", "")),
            "source": {"file": str(csv_path), "row": idx, "description": desc},
        }
        out.append(rec)

    return out

def main() -> int:
    ap = argparse.ArgumentParser(description="Import Thinkorswim positions CSV into ~/.cache/jerboa/positions.v1.json")
    ap.add_argument("--csv", default="", help="Path to a Thinkorswim positions CSV export")
    ap.add_argument("--search-dir", action="append", default=[], help="Additional directory to search for a positions CSV")
    ap.add_argument("--out", default=str(Path.home() / ".cache/jerboa/positions.v1.json"))
    args = ap.parse_args()

    out_path = _expand(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    csv_path: Optional[Path] = _expand(args.csv) if args.csv else None
    if csv_path and not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        return 2

    if csv_path is None:
        search_dirs = SEARCH_DIRS_DEFAULT + args.search_dir
        csv_path = _pick_latest_csv(search_dirs)

    if csv_path is None:
        print("NO CSV FOUND.")
        print("Put a Thinkorswim positions export CSV in one of these folders, then rerun:")
        for d in SEARCH_DIRS_DEFAULT:
            print(f" - {os.path.expanduser(d)}")
        print("")
        print("Or run with an explicit file:")
        print("  jerboa-market-health-positions-refresh --csv /path/to/your_positions.csv")
        return 0

    positions = _parse_positions(csv_path)

    payload = {
        "schema": SCHEMA,
        "asof": _iso_now(),
        "source": {"type": "thinkorswim_csv", "file": str(csv_path)},
        "positions": positions,
        "summary": {
            "count": len(positions),
            "equities": sum(1 for p in positions if p["asset_type"] == "equity"),
            "options": sum(1 for p in positions if p["asset_type"] == "option"),
            "symbols": sorted({p["symbol"] for p in positions}),
        },
    }

    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")
    print(f"OK: wrote {out_path}")
    print(f"OK: imported {len(positions)} positions from {csv_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
