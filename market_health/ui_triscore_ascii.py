from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CACHE = Path(os.path.expanduser("~/.cache/jerboa"))
POS_P = CACHE / "positions.v1.json"
REC_P = CACHE / "recommendations.v1.json"
UI_P = CACHE / "market_health.ui.v1.json"
SECT_P = CACHE / "market_health.sectors.json"
FS_P = CACHE / "forecast_scores.v1.json"

# ---------- ANSI ----------
RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RED = "\x1b[31m"
YEL = "\x1b[33m"
GRN = "\x1b[32m"

CAT_KEYS = ("A", "B", "C", "D", "E")


def _c_for_digit(v: Optional[int]) -> str:
    if v is None:
        return DIM
    if v >= 2:
        return GRN
    if v == 1:
        return YEL
    return RED


def _digit(x: Any) -> str:
    if isinstance(x, bool):
        x = int(x)
    if not isinstance(x, (int, float)):
        return f"{DIM}-{RESET}"
    v = int(x)
    if v < 0 or v > 2:
        return f"{DIM}?{RESET}"
    return f"{_c_for_digit(v)}{v}{RESET}"


def tri(c: Any, h1: Any, h5: Any) -> str:
    return f"{_digit(c)}{_digit(h1)}{_digit(h5)}"


def load(p: Path) -> Dict[str, Any]:
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def pct(sum_score: Optional[int], denom: int) -> Optional[float]:
    if sum_score is None or denom <= 0:
        return None
    return float(sum_score) / float(denom)


def pct_str(p: Optional[float]) -> str:
    if p is None:
        return f"{DIM}n/a{RESET}"
    col = GRN if p >= 0.60 else (YEL if p >= 0.40 else RED)
    return f"{col}{int(round(p * 100)):>3d}%{RESET}"


# ---------- payload discovery ----------
def looks_like_payload(d: Dict[str, Any]) -> bool:
    if "categories" in d and isinstance(d["categories"], dict):
        c = d["categories"]
        return all(k in c for k in CAT_KEYS)
    return all(k in d for k in CAT_KEYS)


def find_payload_for_symbol(obj: Any, sym: str) -> Optional[Dict[str, Any]]:
    sym_u = sym.upper()
    if isinstance(obj, dict):
        s = obj.get("symbol")
        if (
            isinstance(s, str)
            and s.strip().upper() == sym_u
            and looks_like_payload(obj)
        ):
            return obj
        for v in obj.values():
            got = find_payload_for_symbol(v, sym_u)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = find_payload_for_symbol(v, sym_u)
            if got:
                return got
    return None


def find_any_payload(obj: Any) -> Optional[Dict[str, Any]]:
    if isinstance(obj, dict):
        if looks_like_payload(obj):
            return obj
        for v in obj.values():
            got = find_any_payload(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = find_any_payload(v)
            if got:
                return got
    return None


def cat_node(payload: Dict[str, Any], cat: str) -> Any:
    if "categories" in payload and isinstance(payload["categories"], dict):
        return payload["categories"].get(cat)
    return payload.get(cat)


def checks(payload: Optional[Dict[str, Any]], cat: str) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    node = cat_node(payload, cat)
    if isinstance(node, dict) and isinstance(node.get("checks"), list):
        return [c for c in node["checks"] if isinstance(c, dict)]
    if isinstance(node, list):
        return [c for c in node if isinstance(c, dict)]
    return []


def score_at(chks: List[Dict[str, Any]], i: int) -> Optional[int]:
    if i < 0 or i >= len(chks):
        return None
    sc = chks[i].get("score")
    if isinstance(sc, (int, float)):
        return int(sc)
    return None


def sum_checks(chks: List[Dict[str, Any]]) -> int:
    t = 0
    for c in chks[:6]:
        sc = c.get("score")
        if isinstance(sc, (int, float)):
            t += int(sc)
    return t


def sum_payload(payload: Optional[Dict[str, Any]]) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    tot = 0
    for cat in CAT_KEYS:
        tot += sum_checks(checks(payload, cat))
    return tot


def extract_held_symbols(pos_doc: Dict[str, Any]) -> List[str]:
    # best-effort: find all .symbol fields anywhere
    out: List[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            s = x.get("symbol")
            if isinstance(s, str) and s.strip():
                out.append(s.strip().upper())
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(pos_doc)
    # stable unique
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def extract_sector_universe(ui_doc: Dict[str, Any]) -> List[str]:
    # heuristic: find largest list of dict rows that contain "symbol"/"sec"/"ticker"
    candidates: List[List[Dict[str, Any]]] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if (
                    k in ("rows", "sectors", "sector_rows")
                    and isinstance(v, list)
                    and v
                    and isinstance(v[0], dict)
                ):
                    if any(key in v[0] for key in ("symbol", "sec", "ticker")):
                        candidates.append(v)  # type: ignore[arg-type]
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(ui_doc)
    rows = max(candidates, key=len) if candidates else []
    syms: List[str] = []
    for r in rows:
        s = None
        for k in ("symbol", "sec", "ticker"):
            if isinstance(r.get(k), str):
                s = r[k].strip().upper()
                break
        if s:
            syms.append(s)
    return sorted(set(syms))


def get_horizons(fs_doc: Dict[str, Any]) -> Tuple[int, int]:
    hs = fs_doc.get("horizons_trading_days")
    vals: List[int] = []
    if isinstance(hs, list):
        for h in hs:
            try:
                vals.append(int(h))
            except Exception:
                pass
    vals = sorted(set(vals))
    if 1 in vals and 5 in vals:
        return 1, 5
    if len(vals) >= 2:
        return vals[0], vals[1]
    if len(vals) == 1:
        return vals[0], vals[0]
    return 1, 5


def current_payload(
    sym: str, sect_doc: Dict[str, Any], ui_doc: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    # try sectors doc first (usually richer), then UI doc
    got = find_payload_for_symbol(sect_doc, sym)
    if got:
        return got
    got = find_payload_for_symbol(ui_doc, sym)
    if got:
        return got
    return None


def forecast_payload(
    sym: str, H: int, fs_doc: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    scores = fs_doc.get("scores")
    if not isinstance(scores, dict):
        return None
    by_h = scores.get(sym)
    if not isinstance(by_h, dict):
        return None
    raw = by_h.get(str(H), by_h.get(H))
    if raw is None:
        return None
    if isinstance(raw, dict) and looks_like_payload(raw):
        return raw
    return find_any_payload(raw)


def render_positions_triscore_ascii() -> str:
    pos_doc = load(POS_P)
    ui_doc = load(UI_P)
    sect_doc = load(SECT_P)
    fs_doc = load(FS_P)

    held = extract_held_symbols(pos_doc)
    sector_universe = set(extract_sector_universe(ui_doc))

    sector_held = [s for s in held if s in sector_universe]
    unmapped = [s for s in held if s not in sector_universe]

    sym_filter = (os.environ.get("SYM") or "").strip().upper()
    if sym_filter:
        sector_held = [s for s in sector_held if s == sym_filter]
        unmapped = [s for s in unmapped if s == sym_filter]

    h1, h5 = get_horizons(fs_doc)

    lines: List[str] = []
    lines.append("My Positions — Tri-Score Prototype (read-only)")
    lines.append("Each cell shows C/H1/H5 (digits 0=red, 1=yellow, 2=green).")
    lines.append(f"cache={CACHE}")
    lines.append(f"horizons: H1={h1}  H5={h5}")
    lines.append("")

    # If no sector-held symbols, still show unmapped note
    for sym in sector_held:
        cur = current_payload(sym, sect_doc, ui_doc)
        f1 = forecast_payload(sym, h1, fs_doc)
        f5 = forecast_payload(sym, h5, fs_doc)

        cur_sum = sum_payload(cur)
        f1_sum = sum_payload(f1)
        f5_sum = sum_payload(f5)

        denom = 60  # 5 cats * 6 checks * max score 2
        lines.append(
            f"== {sym} ==  Totals (C/H1/H5):  {pct_str(pct(cur_sum, denom))}  {pct_str(pct(f1_sum, denom))}  {pct_str(pct(f5_sum, denom))}"
        )
        lines.append("")
        lines.append(
            f"{'Factor':<18}  {'1':>3} {'2':>3} {'3':>3} {'4':>3} {'5':>3} {'6':>3}   Tot(C/H1/H5)"
        )
        lines.append("-" * 68)

        for cat, name in [
            ("A", "Announcements"),
            ("B", "Backdrop"),
            ("C", "Crowding"),
            ("D", "Danger"),
            ("E", "Environment"),
        ]:
            c_ch = checks(cur, cat)
            h1_ch = checks(f1, cat)
            h5_ch = checks(f5, cat)

            cells = []
            for i in range(6):
                cells.append(
                    tri(score_at(c_ch, i), score_at(h1_ch, i), score_at(h5_ch, i))
                )

            c_tot = sum_checks(c_ch)
            h1_tot = sum_checks(h1_ch)
            h5_tot = sum_checks(h5_ch)

            left = f"{cat} {name}"
            lines.append(
                f"{left:<18}  "
                + " ".join(f"{c:>3}" for c in cells)
                + f"  {c_tot}/{h1_tot}/{h5_tot}"
            )

        lines.append("")
        if unmapped:
            lines.append(
                f"{DIM}Unmapped (not sector ETFs): {', '.join(unmapped)}{RESET}"
            )
        lines.append("")

    if not sector_held:
        if unmapped:
            lines.append(
                f"{DIM}Unmapped (not sector ETFs): {', '.join(unmapped)}{RESET}"
            )
        else:
            lines.append(f"{DIM}No sector ETF positions detected.{RESET}")
        lines.append("")

    lines.append(
        f"{DIM}Note:{RESET} C digit comes from current health scoring; H1/H5 digits come from forecast_scores.v1.json."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_positions_triscore_ascii())
