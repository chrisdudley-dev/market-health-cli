from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# ANSI (terminal-only; disable via mono=True)
RESET = "\x1b[0m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
YEL = "\x1b[33m"
GRN = "\x1b[32m"

CAT_KEYS = ("A", "B", "C", "D", "E")
CAT_LABELS = {
    "A": "Announcements",
    "B": "Backdrop",
    "C": "Crowding",
    "D": "Danger",
    "E": "Environment",
}


def _pal(mono: bool) -> Dict[str, str]:
    if mono:
        return {"RESET": "", "DIM": "", "RED": "", "YEL": "", "GRN": ""}
    return {"RESET": RESET, "DIM": DIM, "RED": RED, "YEL": YEL, "GRN": GRN}


def _load_json(p: Path) -> Dict[str, Any]:
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _looks_like_payload(d: Dict[str, Any]) -> bool:
    if "categories" in d and isinstance(d["categories"], dict):
        c = d["categories"]
        return all(k in c for k in CAT_KEYS)
    return all(k in d for k in CAT_KEYS)


def _find_payload(obj: Any, sym: str) -> Optional[Dict[str, Any]]:
    sym = sym.upper()
    if isinstance(obj, dict):
        s = obj.get("symbol")
        if isinstance(s, str) and s.strip().upper() == sym and _looks_like_payload(obj):
            return obj
        for v in obj.values():
            got = _find_payload(v, sym)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_payload(v, sym)
            if got:
                return got
    return None


def _cat_node(payload: Dict[str, Any], cat: str) -> Any:
    if "categories" in payload and isinstance(payload["categories"], dict):
        return payload["categories"].get(cat)
    return payload.get(cat)


def _checks(payload: Optional[Dict[str, Any]], cat: str) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    node = _cat_node(payload, cat)
    if isinstance(node, dict) and isinstance(node.get("checks"), list):
        return [c for c in node["checks"] if isinstance(c, dict)]
    if isinstance(node, list):
        return [c for c in node if isinstance(c, dict)]
    return []


def _sum_scores(chks: List[Dict[str, Any]]) -> int:
    t = 0
    for c in chks:
        sc = c.get("score")
        if isinstance(sc, (int, float)):
            t += int(sc)
    return t


def _c_for_digit(v: Optional[int], pal: Dict[str, str]) -> str:
    if v is None:
        return pal["DIM"]
    if v >= 2:
        return pal["GRN"]
    if v == 1:
        return pal["YEL"]
    return pal["RED"]


def _digit(x: Any, pal: Dict[str, str]) -> str:
    if isinstance(x, bool):
        x = int(x)
    if not isinstance(x, (int, float)):
        return f"{pal['DIM']}-{pal['RESET']}"
    v = int(x)
    if v < 0 or v > 2:
        return f"{pal['DIM']}?{pal['RESET']}"
    return f"{_c_for_digit(v, pal)}{v}{pal['RESET']}"


def _tri(c: Any, h1: Any, h5: Any, pal: Dict[str, str]) -> str:
    return f"{_digit(c, pal)}{_digit(h1, pal)}{_digit(h5, pal)}"


def _pct_str(sum_score: int, denom: int, pal: Dict[str, str]) -> str:
    p = (float(sum_score) / float(denom)) if denom > 0 else 0.0
    col = pal["GRN"] if p >= 0.60 else (pal["YEL"] if p >= 0.40 else pal["RED"])
    return f"{col}{int(round(p * 100)):>3d}%{pal['RESET']}"


def _payload_from_forecast(
    fs_doc: Dict[str, Any], sym: str, H: int
) -> Optional[Dict[str, Any]]:
    scores = fs_doc.get("scores")
    if not isinstance(scores, dict):
        return None
    by_h = scores.get(sym)
    if not isinstance(by_h, dict):
        return None
    if str(H) in by_h and isinstance(by_h[str(H)], dict):
        return by_h[str(H)]
    if H in by_h and isinstance(by_h[H], dict):
        return by_h[H]
    for k, v in by_h.items():
        if str(k) == str(H) and isinstance(v, dict):
            return v
    return None


def render_positions_triscore(
    *, cache_dir: Optional[str] = None, mono: bool = False, max_rows: int = 8, sector_style=None,
    current_sectors: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Read-only Tri-Score positions panel.
    Each cell is C/H1/H5 where:
      - C  = current health scoring (market_health.ui.v1.json OR market_health.sectors.json)
      - H1 = forecast horizon 1 (forecast_scores.v1.json)
      - H5 = forecast horizon 5 (forecast_scores.v1.json)
    Returns a string (no printing, no cache writes).
    """
    pal = _pal(mono)

    cd = Path(cache_dir) if cache_dir else Path(os.path.expanduser("~/.cache/jerboa"))
    pos_p = cd / "positions.v1.json"
    ui_p = cd / "market_health.ui.v1.json"
    sect_p = cd / "market_health.sectors.json"
    fs_p = cd / "forecast_scores.v1.json"

    pos_doc = _load_json(pos_p)
    fs_doc = _load_json(fs_p)
    cur_doc = ({"sectors": current_sectors} if current_sectors is not None else (_load_json(ui_p) or _load_json(sect_p)))

    held: List[str] = []
    unmapped: List[str] = []
    pos_rows = pos_doc.get("positions") or []
    if isinstance(pos_rows, dict):
        pos_rows = pos_rows.get("positions") or []

    for row in pos_rows:
        if isinstance(row, dict) and isinstance(row.get("symbol"), str):
            sym = row["symbol"].strip().upper()
            if sym.startswith("XL") and len(sym) <= 5:
                held.append(sym)
            else:
                unmapped.append(sym)
    held = sorted(set(held))
    if isinstance(max_rows, int) and max_rows > 0:
        held = held[:max_rows]

    if not held:
        msg = "No positions detected yet (or no sector ETF positions mapped)."
        if unmapped:
            msg += f" Unmapped symbols: {', '.join(sorted(set(unmapped)))}"
        return msg

    # choose horizons: prefer 1 and 5 if present, else min/max
    H1, H5 = 1, 5
    horizons = fs_doc.get("horizons_trading_days")
    if isinstance(horizons, list):
        hs: List[int] = []
        for h in horizons:
            try:
                hs.append(int(h))
            except Exception:
                pass
        hs = sorted(set(hs))
        if hs:
            H1 = 1 if 1 in hs else hs[0]
            H5 = 5 if 5 in hs else hs[-1]

    denom_all = len(CAT_KEYS) * 6 * 2  # 5 cats * 6 checks * max score 2

    lines: List[str] = []
    lines.append("My Positions — Tri-Score (read-only)")
    lines.append("Each cell shows C/H1/H5 (digits 0=bad, 1=mixed, 2=good).")
    lines.append(f"cache={cd}")
    lines.append(f"horizons: H{H1} and H{H5}")
    lines.append("")

    for sym in held:
        cur_payload = _find_payload(cur_doc, sym)
        h1_payload = _payload_from_forecast(fs_doc, sym, H1)
        h5_payload = _payload_from_forecast(fs_doc, sym, H5)

        cur_sum = h1_sum = h5_sum = 0
        for cat in CAT_KEYS:
            cur_sum += _sum_scores(_checks(cur_payload, cat))
            h1_sum += _sum_scores(_checks(h1_payload, cat))
            h5_sum += _sum_scores(_checks(h5_payload, cat))

        lines.append(
            f"──────────────────────── Tri-Score – {sym} ────────────────────────"
        )
        lines.append(
            f"Totals (C/H{H1}/H{H5}):  "
            f"{_pct_str(cur_sum, denom_all, pal)}  "
            f"{_pct_str(h1_sum, denom_all, pal)}  "
            f"{_pct_str(h5_sum, denom_all, pal)}"
        )
        lines.append("")
        lines.append(f"{'Factor':<18}  1   2   3   4   5   6   Tot(C/H{H1}/H{H5})")
        lines.append(
            "--------------------------------------------------------------------"
        )

        for cat in CAT_KEYS:
            cur = _checks(cur_payload, cat)
            h1 = _checks(h1_payload, cat)
            h5 = _checks(h5_payload, cat)

            cells: List[str] = []
            cur_cat = h1_cat = h5_cat = 0
            for i in range(6):
                c_sc = cur[i].get("score") if i < len(cur) else None
                h1_sc = h1[i].get("score") if i < len(h1) else None
                h5_sc = h5[i].get("score") if i < len(h5) else None
                cells.append(_tri(c_sc, h1_sc, h5_sc, pal))
                if isinstance(c_sc, (int, float)):
                    cur_cat += int(c_sc)
                if isinstance(h1_sc, (int, float)):
                    h1_cat += int(h1_sc)
                if isinstance(h5_sc, (int, float)):
                    h5_cat += int(h5_sc)

            label = f"{cat} {CAT_LABELS.get(cat, cat)}"
            lines.append(
                f"{label:<18}  " + " ".join(cells) + f"  {cur_cat}/{h1_cat}/{h5_cat}"
            )

        if unmapped:
            lines.append("")
            lines.append(
                f"Unmapped (not sector ETFs): {', '.join(sorted(set(unmapped)))}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
