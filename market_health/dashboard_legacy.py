from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
import argparse


def _unpack_scores(res):
    """Compat: allow compute_scores to return either rows or (rows, meta)."""
    if isinstance(res, tuple) and len(res) == 2:
        return res
    return res, None


ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
DETAIL_HDR_RE = re.compile(r"^\s*[─-]*\s*Details\s+[–-]\s+([A-Z0-9]+)\s*[─-]*\s*$")

CACHE_DIR = Path.home() / ".cache" / "jerboa"
REC_PATH = CACHE_DIR / "recommendations.v1.json"

# Try common position-cache names (varies by build)
POS_CANDIDATES = [
    CACHE_DIR / "positions.v1.json",
    CACHE_DIR / "positions.v0.json",
    CACHE_DIR / "positions.json",
    CACHE_DIR / "market_health.positions.json",
]

RST = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"


def c(s: str, color: str) -> str:
    return f"{color}{s}{RST}"


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def read_json(p: Path) -> dict[str, Any]:
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def sanitize_args(argv: list[str]) -> list[str]:
    # Never allow caller to override our --topk (we need all details, then we choose)
    out: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--topk":
            i += 2 if i + 1 < len(argv) else 1
            continue
        out.append(argv[i])
        i += 1
    return out


def run_core_ui(user_args: list[str]) -> str:
    env = dict(os.environ)
    env.setdefault("FORCE_COLOR", "1")
    env.setdefault("CLICOLOR_FORCE", "1")
    env.setdefault("PY_COLORS", "1")

    args = sanitize_args(user_args)
    cmd = [sys.executable, "-m", "market_health.market_ui", "--topk", "99", *args]
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env
    )
    return proc.stdout if proc.stdout.strip() else proc.stderr


def split_core_output(core_text: str) -> tuple[str, dict[str, str], list[str]]:
    """
    prefix_text: banner+overview (before first Details block)
    detail_blocks: sym -> raw block text (ANSI preserved)
    detail_order : symbols in core order
    """
    lines = core_text.splitlines(True)
    plain = [strip_ansi(x) for x in lines]

    headers: list[tuple[int, str]] = []
    for i, ln in enumerate(plain):
        m = DETAIL_HDR_RE.match(ln.strip("\n"))
        if m:
            headers.append((i, m.group(1).strip()))

    if not headers:
        return core_text, {}, []

    prefix = "".join(lines[: headers[0][0]])
    blocks: dict[str, str] = {}
    order: list[str] = []

    for idx, (start_i, sym) in enumerate(headers):
        end_i = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        blk = "".join(lines[start_i:end_i]).rstrip("\n")
        blocks[sym] = blk
        order.append(sym)

    return prefix, blocks, order


def strip_core_overview(prefix_text: str) -> str:
    # Remove the core sector-only overview table so we can replace it with expanded A–E.
    lines = prefix_text.splitlines(True)
    out = []
    skipping = False
    for ln in lines:
        plain = strip_ansi(ln)
        if "Overview (A–E totals per sector)" in plain:
            skipping = True
            continue
        if skipping:
            # stop skipping when we hit the Pi Grid header
            if "Market Health – Pi Grid" in plain:
                skipping = False
                out.append(ln)
            continue
        out.append(ln)
    return "".join(out)


def parse_overview_totals(prefix_text: str) -> tuple[list[str], dict[str, float]]:
    """
    Utility = (last x/y on the XL* line). Ignores percents completely (wrap-safe).
    Returns (ordered_syms, util_map).
    """
    util: dict[str, float] = {}
    order: list[str] = []
    for ln in strip_ansi(prefix_text).splitlines():
        m = re.match(r"^\s*([A-Z0-9][A-Z0-9\.\-]{1,15})\b", ln)
        if not m:
            continue
        sym = m.group(1)
        if sym in {"SECTOR", "SYM", "FACTOR", "TOTAL"}:
            continue
        pairs = re.findall(r"(\d+)/(\d+)", ln)
        if not pairs:
            continue
        a_s, b_s = pairs[-1]  # Total column
        try:
            a = int(a_s)
            b = int(b_s)
        except ValueError:
            continue
        if b > 0:
            util[sym] = a / b
            if sym not in order:
                order.append(sym)
    return order, util


def extract_symbols_from_positions(doc: dict[str, Any]) -> list[str]:
    syms: list[str] = []

    v = doc.get("symbols")
    if isinstance(v, list):
        for x in v:
            if x is not None:
                syms.append(str(x).upper().strip())

    v = doc.get("positions")
    if isinstance(v, list):
        for row in v:
            if isinstance(row, dict):
                s = row.get("symbol") or row.get("sym") or row.get("ticker")
                if s:
                    syms.append(str(s).upper().strip())

    seen = set()
    out: list[str] = []
    for s in syms:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _strip_prefix_sections(text: str) -> str:
    if not isinstance(text, str):
        return text

    starts = []
    for marker in (
        "Overview (A–E totals per universe)",
        "Overview (A-E totals per universe)",
        "Market Health – Pi Grid",
        "Market Health - Pi Grid",
    ):
        idx = text.find(marker)
        if idx >= 0:
            starts.append(idx)

    if not starts:
        return text

    cut = min(starts)
    return text[:cut].rstrip() + "\n\n"


def pick_positions(detail_blocks: dict[str, str], rec_doc: dict[str, Any]) -> list[str]:
    # 1) real positions cache (if it exists)
    for p in POS_CANDIDATES:
        doc = read_json(p)
        if doc:
            syms = extract_symbols_from_positions(doc)
            chosen = [s for s in syms if s in detail_blocks]
            if chosen:
                return chosen

    # 2) fallback: held_scored from recommendations cache
    rec = None
    if isinstance(rec_doc, dict):
        rec = rec_doc.get("recommendation")
        if not isinstance(rec, dict):
            # Accept flat v1 cache schema (keys live at top-level)
            if any(
                k in rec_doc
                for k in (
                    "action",
                    "why",
                    "swap_candidates",
                    "threshold",
                    "best",
                    "weakest",
                    "held_syms",
                    "status",
                )
            ):
                rec = rec_doc

    diag = rec.get("diagnostics") if isinstance(rec, dict) else None
    held = diag.get("held_scored") if isinstance(diag, dict) else None
    if isinstance(held, list):
        chosen = [str(x) for x in held if str(x) in detail_blocks]
        if chosen:
            return chosen

    return []


def grade_letter(pct: int) -> tuple[str, str]:
    if pct >= 60:
        return "B", GREEN
    if pct >= 45:
        return "H", YELLOW
    return "S", RED


def _snapshot_order_util(doc: dict) -> tuple[list[str], dict[str, float]]:
    data = doc.get("data") or {}
    rows = data.get("sectors")
    if not isinstance(rows, list):
        return [], {}
    order = []
    util = {}
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get("symbol"), str):
            order.append(r["symbol"].strip().upper())
    denom = 5 * 6 * 2  # 60
    for r in rows:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").upper().strip()
        cats = r.get("categories")
        if not sym or not isinstance(cats, dict):
            continue
        total = 0
        maxp = 0
        for cat in ("A", "B", "C", "D", "E"):
            node = cats.get(cat)
            if not isinstance(node, dict):
                continue
            checks = node.get("checks")
            if not isinstance(checks, list):
                continue
            for chk in checks:
                if isinstance(chk, dict) and isinstance(chk.get("score"), int):
                    total += int(chk["score"])
                    maxp += 2
        util[sym] = float(total / maxp) if maxp else float(total / denom)
    seen = set()
    order2 = []
    for x in order:
        if x and x not in seen:
            seen.add(x)
            order2.append(x)
    return order2, util


def render_pi_grid(order: list[str], util: dict[str, float]) -> str:
    if not order:
        return ""
    cols = 4

    def box(sym: str, pct: int) -> list[str]:
        letter, col = grade_letter(pct)
        return [
            "╭──────╮",
            f"│ {sym:<4}│",
            f"│ {c(f'{pct:>3}%', col)} │",
            f"│  {c(letter, col)}   │",
            "╰──────╯",
        ]

    lines: list[str] = []
    lines.append(
        c(
            "────────────────────────────── Market Health – Pi Grid ──────────────────────────────",
            MAGENTA,
        )
    )
    row: list[list[str]] = []
    for i, sym in enumerate(order):
        pct = int(round(util.get(sym, 0.0) * 100))
        row.append(box(sym, pct))
        if (i + 1) % cols == 0:
            for r in range(5):
                lines.append("  ".join(cell[r] for cell in row))
            row = []
    if row:
        for r in range(5):
            lines.append("  ".join(cell[r] for cell in row))
    return "\n".join(lines) + "\n"


def fmt_u(u: float | None) -> str:
    if u is None:
        return "-"
    return f"{u:.3f} / {u * 100:.1f}%"


def render_overview_triscore(order, util, held_syms):
    import io
    import json
    import os
    from pathlib import Path
    from market_health.engine import compute_scores
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    NL = chr(10)
    cache = Path.home() / ".cache" / "jerboa"
    ui_p = cache / "market_health.ui.v1.json"
    fs_p = cache / "forecast_scores.v1.json"
    sectors_p = cache / "market_health.sectors.json"
    inv_p = cache / "inverse_universe.v1.json"

    console = Console(
        record=True,
        force_terminal=True,
        color_system="truecolor",
        width=max(160, int(os.environ.get("COLUMNS", "160"))),
        file=io.StringIO(),
    )

    def _jload(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _norm(sym):
        s = str(sym or "").strip().upper()
        return s if s else ""

    def _to_float(v):
        if isinstance(v, (int, float)):
            return float(v)
        try:
            s = str(v).strip().replace("%", "").replace(",", "")
            if not s:
                return None
            return float(s)
        except Exception:
            return None

    def _to_pct(v):
        n = _to_float(v)
        if n is None:
            return None
        return n / 100.0 if abs(n) > 1.5 else n

    def _fmt_pct(v):
        n = _to_pct(v)
        return "-" if n is None else f"{int(round(n * 100.0)):d}%"

    def _fmt_num(v):
        n = _to_float(v)
        if n is None:
            return "-"
        return f"{n:.2f}"

    def _score_style(v):
        n = _to_pct(v)
        if n is None:
            return "dim"
        if n >= 0.60:
            return "bold green"
        if n >= 0.40:
            return "bold yellow"
        return "bold red"

    def _num_style(v):
        return "bold cyan" if isinstance(v, (int, float)) else "dim"

    def _state_style(s):
        s = str(s or "")
        if "near_damage_zone" in s:
            return "bold red"
        if "breakout_ready" in s:
            return "bold green"
        if "reclaim_ready" in s or "overhead_heavy" in s:
            return "bold yellow"
        return "white"

    def _walk_find(obj, keys):
        want = {str(k).lower() for k in keys}
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in want and v not in (None, "", [], {}):
                    return v
            for v in obj.values():
                found = _walk_find(v, keys)
                if found not in (None, "", [], {}):
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _walk_find(item, keys)
                if found not in (None, "", [], {}):
                    return found
        return None

    def _rowmaps_from_any(doc):
        out = {}

        allowed = set()
        for s in order or []:
            ns = _norm(s)
            if ns:
                allowed.add(ns)
        for s in held_syms or []:
            ns = _norm(s)
            if ns:
                allowed.add(ns)
        if isinstance(util, dict):
            for s in util.keys():
                ns = _norm(s)
                if ns:
                    allowed.add(ns)

        def _accept(sym):
            sym = _norm(sym)
            if not sym:
                return False
            if allowed:
                return sym in allowed
            return False

        def ingest(obj):
            if isinstance(obj, list):
                for item in obj:
                    ingest(item)
                return

            if not isinstance(obj, dict):
                return

            sym = _norm(obj.get("symbol") or obj.get("sym") or obj.get("ticker"))
            if _accept(sym):
                out.setdefault(sym, {}).update(obj)

            for k in ("rows", "items", "data", "sectors", "state", "scores"):
                v = obj.get(k)
                if isinstance(v, (list, dict)):
                    ingest(v)

            for v in obj.values():
                if isinstance(v, (list, dict)):
                    ingest(v)

        ingest(doc)
        return out

    def _forecast_horizons(fs_doc):
        hs = fs_doc.get("horizons_trading_days")
        out = []
        if isinstance(hs, list):
            for h in hs:
                try:
                    out.append(int(h))
                except Exception:
                    pass
        return (out[0], out[1]) if len(out) >= 2 else (1, 5)

    def _forecast_util(fs_doc, sym, horizon_days):
        scores = fs_doc.get("scores")
        if not isinstance(scores, dict):
            return None
        by_h = scores.get(sym)
        if not isinstance(by_h, dict):
            return None
        payload = by_h.get(str(horizon_days), by_h.get(horizon_days))
        if not isinstance(payload, dict):
            return None

        fs = payload.get("forecast_score")
        if isinstance(fs, (int, float)):
            v = float(fs)
            return v / 100.0 if v > 1.5 else v

        pts = payload.get("points")
        mx = payload.get("max_points")
        if isinstance(pts, (int, float)) and isinstance(mx, (int, float)) and mx:
            return float(pts) / float(mx)

        return None

    def _first_pct(*vals):
        for v in vals:
            n = _to_pct(v)
            if n is not None:
                return n
        return None

    def _first_num(*vals):
        for v in vals:
            n = _to_float(v)
            if n is not None:
                return n
        return None

    def _sum_cat_pct(row):
        cats = (row or {}).get("categories", {})
        if not isinstance(cats, dict):
            return None
        pts = 0
        mx = 0
        for cat in cats.values():
            if not isinstance(cat, dict):
                continue
            checks = cat.get("checks")
            if not isinstance(checks, list):
                continue
            for chk in checks:
                if not isinstance(chk, dict):
                    continue
                sc = chk.get("score")
                if isinstance(sc, (int, float)):
                    pts += int(sc)
                    mx += 2
        return (pts / mx) if mx else None

    def _canonical_overview_rows(symbols):
        out = {}
        want = []
        for s in symbols or []:
            ns = _norm(s)
            if ns and ns not in want:
                want.append(ns)

        if not want:
            return out

        try:
            res = compute_scores(sectors=want, period="6mo", interval="1d")
            rows2, _ = _unpack_scores(res)
        except Exception:
            rows2 = []

        if isinstance(rows2, list):
            for it in rows2:
                if not isinstance(it, dict):
                    continue
                s2 = _norm(it.get("symbol") or it.get("sym") or it.get("ticker"))
                if s2:
                    out[s2] = it
        return out

    ui = _jload(ui_p)
    fs = _jload(fs_p)
    sectors = _jload(sectors_p)
    inv = _jload(inv_p)

    data = ui.get("data") if isinstance(ui, dict) else {}
    sector_rows = _rowmaps_from_any(sectors)
    ui_sector_rows = _rowmaps_from_any(
        data.get("sectors") if isinstance(data, dict) else {}
    )
    state_rows = _rowmaps_from_any(data.get("state") if isinstance(data, dict) else {})

    rows = {}
    for sym, row in sector_rows.items():
        rows.setdefault(sym, {}).update(row)
    for sym, row in ui_sector_rows.items():
        rows.setdefault(sym, {}).update(row)
    for sym, row in state_rows.items():
        rows.setdefault(sym, {}).update(row)

    inv_to_long = {}
    pairs = inv.get("pairs") if isinstance(inv, dict) else None
    if isinstance(pairs, list):
        for p in pairs:
            if not isinstance(p, dict):
                continue
            long_sym = _norm(p.get("long"))
            inv_sym = _norm(p.get("inverse"))
            if long_sym:
                inv_to_long[long_sym] = long_sym
            if long_sym and inv_sym:
                inv_to_long[inv_sym] = long_sym

    for _src, _dst in _proxy_overrides().items():
        _s = _norm(_src)
        _d = _norm(_dst)
        if _s and _d:
            inv_to_long[_s] = _d

    score_keys = []
    scores = fs.get("scores")
    if isinstance(scores, dict):
        score_keys = [_norm(k) for k in scores.keys() if _norm(k)]

    universe = set()
    universe.update(_norm(s) for s in (order or []) if _norm(s))
    universe.update(score_keys)
    universe.update(rows.keys())
    universe.update(inv_to_long.keys())

    universe = {
        s for s in universe if s and (s in rows or s in score_keys or s in inv_to_long)
    }
    universe = {s for s in universe if s not in {"XLV", "CSWC"}}

    H1, H5 = _forecast_horizons(fs)

    display_rows = []
    util_map = util if isinstance(util, dict) else {}

    extras_map = {}
    try:
        missing_syms = [
            s
            for s in sorted(universe)
            if s
            and (
                not isinstance(rows.get(s), dict)
                or not isinstance((rows.get(s) or {}).get("categories"), dict)
            )
        ]
        if missing_syms:
            extra_rows, _ = _unpack_scores(
                compute_scores(sectors=missing_syms, period="6mo", interval="1d")
            )
            for it in extra_rows:
                if not isinstance(it, dict):
                    continue
                s2 = _norm(it.get("symbol") or it.get("sym") or it.get("ticker"))
                if s2:
                    extras_map[s2] = it
    except Exception:
        extras_map = {}

    canonical_syms = set()
    for s in sorted(universe):
        ns = _norm(s)
        if ns:
            canonical_syms.add(ns)
        ps = _norm(_proxy_for_symbol(s, inv_to_long))
        if ps:
            canonical_syms.add(ps)

    canonical_rows = {}  # disabled: overview must not recompute live scores

    for sym in sorted(universe):
        proxy_sym = _proxy_for_symbol(sym, inv_to_long)
        row = rows.get(sym, {})
        proxy_row = rows.get(proxy_sym, {})
        score_row = extras_map.get(sym) or row
        proxy_score_row = extras_map.get(proxy_sym) or proxy_row

        canonical_row = (
            canonical_rows.get(sym) or canonical_rows.get(proxy_sym) or row or proxy_row
        )

        c_val = _first_pct(
            _sum_cat_pct(score_row),
            _sum_cat_pct(proxy_score_row),
            row.get("c"),
            proxy_row.get("c"),
            _walk_find(score_row, ["c"]),
            _walk_find(proxy_score_row, ["c"]),
        )

        h1_val = _first_pct(
            _forecast_util(fs, sym, H1),
            _forecast_util(fs, proxy_sym, H1),
            row.get("h1"),
            proxy_row.get("h1"),
            _walk_find(row, ["h1", f"h{H1}", "forecast_h1", "forecast_1"]),
            _walk_find(proxy_row, ["h1", f"h{H1}", "forecast_h1", "forecast_1"]),
        )

        h5_val = _first_pct(
            _forecast_util(fs, sym, H5),
            _forecast_util(fs, proxy_sym, H5),
            row.get("h5"),
            proxy_row.get("h5"),
            _walk_find(row, ["h5", f"h{H5}", "forecast_h5", "forecast_5"]),
            _walk_find(proxy_row, ["h5", f"h{H5}", "forecast_h5", "forecast_5"]),
        )

        pieces = []
        if c_val is not None:
            pieces.append((0.50, c_val))
        if h1_val is not None:
            pieces.append((0.25, h1_val))
        if h5_val is not None:
            pieces.append((0.25, h5_val))
        denom = sum(w for w, _ in pieces)
        blend = sum(w * v for w, v in pieces) / denom if denom > 0 else None
        if c_val is not None and h1_val is not None and h5_val is not None:
            blend = (0.50 * c_val) + (0.25 * h1_val) + (0.25 * h5_val)

        sup = _first_num(
            proxy_row.get("sup_atr"),
            proxy_row.get("support_atr"),
            proxy_row.get("supatr"),
            _walk_find(proxy_row, ["sup_atr", "support_atr", "supatr"]),
        )
        res = _first_num(
            proxy_row.get("res_atr"),
            proxy_row.get("resistance_atr"),
            proxy_row.get("resatr"),
            _walk_find(proxy_row, ["res_atr", "resistance_atr", "resatr"]),
        )
        state = (
            proxy_row.get("state")
            or proxy_row.get("risk_state")
            or proxy_row.get("overlay_state")
            or _walk_find(
                proxy_row,
                ["state", "risk_state", "overlay_state", "structure_state", "regime"],
            )
            or "-"
        )
        stop = _first_num(
            proxy_row.get("stop"),
            proxy_row.get("stop_price"),
            proxy_row.get("stop_px"),
            _walk_find(proxy_row, ["stop", "stop_price", "stop_px", "atr_stop"]),
        )
        buy = _first_num(
            proxy_row.get("buy"),
            proxy_row.get("buy_price"),
            proxy_row.get("buy_px"),
            proxy_row.get("entry"),
            proxy_row.get("entry_price"),
            _walk_find(
                proxy_row,
                ["buy", "buy_price", "buy_px", "entry", "entry_price", "buy_trigger"],
            ),
        )

        ss = _structure_summary_for_symbol(fs, sym, horizon=H5)
        if (not isinstance(ss, dict) or not ss) and proxy_sym != sym:
            ss = _structure_summary_for_symbol(fs, proxy_sym, horizon=H5)

        if isinstance(ss, dict) and ss:
            sup = _first_num(
                ss.get("support_cushion_atr"),
                ss.get("support_atr"),
                ss.get("sup_atr"),
                _walk_find(ss, ["support_cushion_atr", "support_atr", "sup_atr"]),
                sup,
            )
            res = _first_num(
                ss.get("overhead_resistance_atr"),
                ss.get("resistance_atr"),
                ss.get("res_atr"),
                _walk_find(
                    ss, ["overhead_resistance_atr", "resistance_atr", "res_atr"]
                ),
                res,
            )
            tags = ss.get("state_tags")
            if isinstance(tags, list) and tags:
                state = ",".join(str(x) for x in tags if x) or state
            else:
                raw_state = (
                    ss.get("state_text")
                    or ss.get("state")
                    or _walk_find(ss, ["state_text", "state", "state_tags"])
                )
                if raw_state not in (None, "", "-"):
                    state = str(raw_state)

            stop = _first_num(
                ss.get("tactical_stop_candidate"),
                ss.get("catastrophic_stop_candidate"),
                ss.get("stop"),
                ss.get("stop_candidate"),
                _walk_find(
                    ss,
                    [
                        "tactical_stop_candidate",
                        "catastrophic_stop_candidate",
                        "stop",
                        "stop_candidate",
                    ],
                ),
                stop,
            )
            buy = _first_num(
                ss.get("stop_buy_candidate"),
                ss.get("breakout_trigger"),
                ss.get("buy"),
                ss.get("buy_candidate"),
                _walk_find(
                    ss,
                    ["stop_buy_candidate", "breakout_trigger", "buy", "buy_candidate"],
                ),
                buy,
            )

        display_rows.append(
            {
                "sym": sym,
                "blend": blend,
                "c": c_val,
                "h1": h1_val,
                "h5": h5_val,
                "sup": sup,
                "res": res,
                "state": str(state),
                "stop": stop,
                "buy": buy,
            }
        )

    display_rows.sort(
        key=lambda r: (
            -1.0 if not isinstance(r["blend"], (int, float)) else -float(r["blend"]),
            r["sym"],
        )
    )

    tbl = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        pad_edge=True,
    )
    tbl.add_column("Sym", justify="left", no_wrap=True)
    tbl.add_column("Blend", justify="right", no_wrap=True)
    tbl.add_column("C", justify="right", no_wrap=True)
    tbl.add_column("H1", justify="right", no_wrap=True)
    tbl.add_column("H5", justify="right", no_wrap=True)
    tbl.add_column("SupATR", justify="right", no_wrap=True)
    tbl.add_column("ResATR", justify="right", no_wrap=True)
    tbl.add_column("State", justify="left", no_wrap=True, width=11, max_width=11)
    tbl.add_column("Stop", justify="right", no_wrap=True)
    tbl.add_column("Buy", justify="right", no_wrap=True)

    for r in display_rows:
        tbl.add_row(
            r["sym"],
            Text(_fmt_pct(r["blend"]), style=_score_style(r["blend"])),
            Text(_fmt_pct(r["c"]), style=_score_style(r["c"])),
            Text(_fmt_pct(r["h1"]), style=_score_style(r["h1"])),
            Text(_fmt_pct(r["h5"]), style=_score_style(r["h5"])),
            Text(_fmt_num(r["sup"]), style=_num_style(r["sup"])),
            Text(_fmt_num(r["res"]), style=_num_style(r["res"])),
            Text(
                _compact_state_tags(r["state"] if r["state"] else "-"),
                style=_state_style(r["state"]),
            ),
            Text(_fmt_num(r["stop"]), style=_num_style(r["stop"])),
            Text(_fmt_num(r["buy"]), style=_num_style(r["buy"])),
        )

    console.print(
        Panel(
            tbl,
            title="Overview (expanded universe, compact tri-score) • all",
            border_style="cyan",
            box=box.SQUARE,
        )
    )
    return console.export_text(styles=True) + NL


def _forecast_scores_doc() -> dict[str, Any]:
    doc = read_json(CACHE_DIR / "forecast_scores.v1.json")
    return doc if isinstance(doc, dict) else {}


def _proxy_overrides() -> dict[str, str]:
    return {
        "CSWC": "XLF",
    }


def _proxy_for_symbol(sym: str, inv_to_long: dict[str, str] | None = None) -> str:
    s = str(sym or "").upper().strip()
    if not s:
        return s
    mapped = _proxy_overrides().get(s)
    if mapped:
        return str(mapped).upper().strip()
    if isinstance(inv_to_long, dict):
        mapped = inv_to_long.get(s)
        if mapped:
            return str(mapped).upper().strip()
    return s


def _load_inverse_map_from_cache():
    out = {}
    try:
        inv_path = CACHE_DIR / "inverse_universe.v1.json"
        doc = read_json(inv_path)
        pairs = doc.get("pairs") if isinstance(doc, dict) else None
        if isinstance(pairs, list):
            for row in pairs:
                if not isinstance(row, dict):
                    continue
                long_sym = str(row.get("long") or "").upper().strip()
                inv_sym = str(row.get("inverse") or "").upper().strip()
                if long_sym:
                    out[long_sym] = long_sym
                if long_sym and inv_sym:
                    out[inv_sym] = long_sym
    except Exception:
        out = {}

    try:
        for src, dst in (_proxy_overrides() or {}).items():
            s = str(src or "").upper().strip()
            d = str(dst or "").upper().strip()
            if s and d:
                out[s] = d
    except Exception:
        pass

    return out


def _forecast_payload_for_symbol(
    scores_doc: dict[str, Any], sym: str, preferred_horizon: int = 5
) -> dict[str, Any]:
    scores = scores_doc.get("scores")
    if not isinstance(scores, dict):
        return {}

    by_h = scores.get(str(sym).upper())
    if not isinstance(by_h, dict):
        return {}

    for h in (preferred_horizon, 1, 5):
        node = by_h.get(str(h), by_h.get(h))
        if isinstance(node, dict):
            return node
    return {}


def _structure_summary_for_symbol(
    fs_doc,
    symbol,
    *,
    horizon=None,
):
    if not isinstance(fs_doc, dict):
        return {}

    scores = fs_doc.get("scores") or {}
    if not isinstance(scores, dict):
        return {}

    sym = str(symbol or "").upper().strip()
    if not sym:
        return {}

    by_h = scores.get(sym) or scores.get(str(symbol)) or {}
    if not isinstance(by_h, dict):
        return {}

    if horizon is None:
        hs = fs_doc.get("horizons_trading_days") or [1, 5]
        try:
            horizon = int(hs[1])
        except Exception:
            horizon = 5

    try:
        hk_int = int(horizon)
    except Exception:
        hk_int = 5

    payload = None
    for hk in (str(hk_int), hk_int):
        cand = by_h.get(hk)
        if isinstance(cand, dict):
            payload = cand
            break

    if not isinstance(payload, dict):
        return {}

    ss = payload.get("structure_summary") or {}
    if not isinstance(ss, dict):
        ss = {}

    out = dict(ss)

    sup = out.get("support_cushion_atr")
    res = out.get("overhead_resistance_atr")
    state_tags = out.get("state_tags") or []
    stop = out.get("catastrophic_stop_candidate")
    buy = out.get("stop_buy_candidate")

    out.setdefault("support_atr", sup)
    out.setdefault("sup_atr", sup)
    out.setdefault("resistance_atr", res)
    out.setdefault("res_atr", res)
    out.setdefault("state", state_tags)
    out.setdefault("state_text", ",".join(str(x) for x in state_tags if x))
    out.setdefault("stop", stop)
    out.setdefault("stop_candidate", stop)
    out.setdefault("buy", buy)
    out.setdefault("buy_candidate", buy)

    if "payload" not in out:
        out["payload"] = payload

    return out


def _fmt_state_tags(tags: Any) -> str:
    if not isinstance(tags, list) or not tags:
        return "-"
    return ", ".join(str(x) for x in tags)


def _render_execution_guidance_widget(
    console, fs_doc: dict[str, Any], sym: str
) -> None:
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    if not isinstance(sym, str) or not sym:
        return

    payload = _forecast_payload_for_symbol(fs_doc, sym, preferred_horizon=5)
    structure = payload.get("structure_summary") if isinstance(payload, dict) else {}
    if not isinstance(structure, dict) or not structure:
        return

    tactical_stop = structure.get("tactical_stop_candidate")
    stop_buy = structure.get("stop_buy_candidate")
    if not isinstance(tactical_stop, (int, float)) and not isinstance(
        stop_buy, (int, float)
    ):
        return

    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(style="bold cyan", no_wrap=True)
    tbl.add_column(no_wrap=False)

    tbl.add_row("tactical stop", _fmt_price(tactical_stop))
    tbl.add_row("stop-buy", _fmt_price(stop_buy))

    console.print(
        Panel(
            tbl,
            title=f"Optional Execution Guidance — {sym}",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )


def _render_risk_overlay_widget(console, fs_doc: dict[str, Any], sym: str) -> None:
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    from market_health.risk_overlay import build_risk_overlay_state

    if not isinstance(sym, str) or not sym:
        return

    payload = _forecast_payload_for_symbol(fs_doc, sym, preferred_horizon=5)
    structure = payload.get("structure_summary") if isinstance(payload, dict) else {}
    if not isinstance(structure, dict) or not structure:
        return

    state = build_risk_overlay_state(symbol=sym, structure_summary=structure)

    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(style="bold cyan", no_wrap=True)
    tbl.add_column(no_wrap=False)

    tbl.add_row("status", str(state.status))
    tbl.add_row("armed", "yes" if state.armed else "no")
    tbl.add_row("catastrophic stop", _fmt_price(state.catastrophic_stop))
    tbl.add_row("breach level", _fmt_price(state.breach_level))
    tbl.add_row("reason", str(state.reason or "-"))

    border = (
        "red" if state.armed else ("yellow" if state.status == "DISARMED" else "white")
    )

    console.print(
        Panel(
            tbl,
            title=f"Risk Overlay — {sym}",
            border_style=border,
            box=box.ROUNDED,
        )
    )


def _render_watch_levels_widget(console, fs_doc: dict[str, Any], sym: str) -> None:
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    if not isinstance(sym, str) or not sym:
        return

    payload = _forecast_payload_for_symbol(fs_doc, sym, preferred_horizon=5)
    structure = payload.get("structure_summary") if isinstance(payload, dict) else {}
    if not isinstance(structure, dict) or not structure:
        return

    support_zone = structure.get("nearest_support_zone")
    resistance_zone = structure.get("nearest_resistance_zone")

    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(style="bold cyan", no_wrap=True)
    tbl.add_column(no_wrap=False)

    tbl.add_row("support", _fmt_zone_triplet(support_zone))
    tbl.add_row("resistance", _fmt_zone_triplet(resistance_zone))
    tbl.add_row("breakout", _fmt_price(structure.get("breakout_trigger")))
    tbl.add_row("breakdown", _fmt_price(structure.get("breakdown_trigger")))
    tbl.add_row("reclaim", _fmt_price(structure.get("reclaim_trigger")))
    tbl.add_row("cushion", _fmt_atr_short(structure.get("support_cushion_atr")))
    tbl.add_row("overhead", _fmt_atr_short(structure.get("overhead_resistance_atr")))
    tbl.add_row("state", _fmt_state_tags(structure.get("state_tags")))

    console.print(
        Panel(
            tbl,
            title=f"Watch Levels / Structure — {sym}",
            border_style="bright_blue",
            box=box.ROUNDED,
        )
    )


def _pair_reason_tag(
    from_structure: dict[str, Any], to_structure: dict[str, Any]
) -> str:
    from_sup = from_structure.get("support_cushion_atr")
    to_sup = to_structure.get("support_cushion_atr")
    from_res = from_structure.get("overhead_resistance_atr")
    to_res = to_structure.get("overhead_resistance_atr")

    from_tags = {str(x) for x in (from_structure.get("state_tags") or [])}
    to_tags = {str(x) for x in (to_structure.get("state_tags") or [])}

    if "near_damage_zone" in from_tags and "breakout_ready" in to_tags:
        return "damage→breakout"

    if (
        isinstance(from_sup, (int, float))
        and isinstance(to_sup, (int, float))
        and to_sup > from_sup
    ):
        return "better cushion"

    if (
        isinstance(from_res, (int, float))
        and isinstance(to_res, (int, float))
        and to_res < from_res
    ):
        return "less overhead"

    if "near_damage_zone" in to_tags and "reclaim_ready" not in to_tags:
        return "damage risk"
    if "reclaim_ready" in to_tags:
        return "reclaim-ready"
    if "breakout_ready" in to_tags:
        return "breakout-ready"

    if "near_damage_zone" in from_tags:
        return "damage risk"

    return ""


def _file_mtime_iso(path):
    try:
        from pathlib import Path
        from datetime import datetime, timezone

        ts = Path(path).stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except Exception:
        return None


def _parse_iso_utc(s):
    try:
        from datetime import datetime, timezone

        s = str(s or "").strip()
        if not s:
            return None
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fmt_age_short(delta_seconds):
    try:
        n = int(max(0, float(delta_seconds)))
    except Exception:
        return "-"
    if n < 60:
        return f"{n}s"
    if n < 3600:
        return f"{n // 60}m"
    if n < 86400:
        return f"{n // 3600}h"
    return f"{n // 86400}d"


def _fresh_bool_from_age(delta_seconds, max_age_seconds):
    try:
        return float(delta_seconds) <= float(max_age_seconds)
    except Exception:
        return None


def _fallback_freshness_bundle(rec_doc, cache_dir):
    from pathlib import Path
    from datetime import datetime, timezone

    rec_doc = rec_doc if isinstance(rec_doc, dict) else {}
    cache_dir = Path(cache_dir)
    now = datetime.now(timezone.utc)

    pos_ts = _file_mtime_iso(cache_dir / "positions.v1.json")
    fc_ts = _file_mtime_iso(cache_dir / "forecast_scores.v1.json")
    snap_ts = _file_mtime_iso(cache_dir / "market_health.ui.v1.json")

    source_ts = rec_doc.get("source_timestamps")
    if not isinstance(source_ts, dict):
        source_ts = {}

    source_ts = {
        "positions": source_ts.get("positions") or pos_ts,
        "forecast": source_ts.get("forecast") or fc_ts,
        "snapshot": source_ts.get("snapshot") or snap_ts,
    }

    freshness = rec_doc.get("freshness")
    if not isinstance(freshness, dict):
        freshness = {}

    pos_dt = _parse_iso_utc(source_ts.get("positions"))
    fc_dt = _parse_iso_utc(source_ts.get("forecast"))
    snap_dt = _parse_iso_utc(source_ts.get("snapshot"))

    pos_age = (now - pos_dt).total_seconds() if pos_dt else None
    fc_age = (now - fc_dt).total_seconds() if fc_dt else None
    snap_age = (now - snap_dt).total_seconds() if snap_dt else None

    freshness = {
        "positions": freshness.get("positions")
        if isinstance(freshness.get("positions"), bool)
        else _fresh_bool_from_age(pos_age, 86400),
        "forecast": freshness.get("forecast")
        if isinstance(freshness.get("forecast"), bool)
        else _fresh_bool_from_age(fc_age, 86400),
        "snapshot": freshness.get("snapshot")
        if isinstance(freshness.get("snapshot"), bool)
        else _fresh_bool_from_age(snap_age, 86400),
    }

    ages = {
        "positions": _fmt_age_short(pos_age) if pos_age is not None else "-",
        "forecast": _fmt_age_short(fc_age) if fc_age is not None else "-",
        "snapshot": _fmt_age_short(snap_age) if snap_age is not None else "-",
    }

    return source_ts, freshness, ages


def render_reco(order, util, rec_doc, held_syms):
    import io
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    NL = chr(10)
    console = Console(
        record=True,
        force_terminal=True,
        color_system="truecolor",
        width=118,
        file=io.StringIO(),
    )

    def _num(v):
        return float(v) if isinstance(v, (int, float)) else None

    def _fmt(v):
        n = _num(v)
        return "-" if n is None else f"{n:.2f}"

    def _fmt_pct_weights(w):
        if not isinstance(w, dict):
            return "-"
        c_w = float(w.get("c", 0.0) or 0.0)
        h1_w = float(w.get("h1", 0.0) or 0.0)
        h5_w = float(w.get("h5", 0.0) or 0.0)
        return f"C {c_w:.0%}  H1 {h1_w:.0%}  H5 {h5_w:.0%}"

    def _score_style(v):
        n = _num(v)
        if n is None:
            return "dim"
        if n >= 0.60:
            return "bold green"
        if n >= 0.40:
            return "bold yellow"
        return "bold red"

    def _delta_style(v, thr=None):
        n = _num(v)
        t = _num(thr)
        if n is None:
            return "dim"
        if t is not None and n >= t:
            return "bold green"
        if n > 0:
            return "yellow"
        if n < 0:
            return "red"
        return "dim"

    def _status_style(s):
        s = str(s or "").upper()
        if s == "READY":
            return "bold green"
        if s == "BLOCKED":
            return "bold red"
        return "bold yellow"

    fs_doc = {}
    try:
        fs_doc = json.loads(
            (Path.home() / ".cache" / "jerboa" / "forecast_scores.v1.json").read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        fs_doc = {}

    def _forecast_horizons():
        hs = fs_doc.get("horizons_trading_days")
        out = []
        if isinstance(hs, list):
            for h in hs:
                try:
                    out.append(int(h))
                except Exception:
                    pass
        if len(out) >= 2:
            return out[0], out[1]
        return 1, 5

    H1, H5 = _forecast_horizons()

    def _forecast_util(sym, horizon_days):
        if not isinstance(sym, str) or not sym:
            return None
        scores = fs_doc.get("scores")
        if not isinstance(scores, dict):
            return None
        by_h = scores.get(sym)
        if not isinstance(by_h, dict):
            return None
        payload = by_h.get(str(horizon_days), by_h.get(horizon_days))
        if not isinstance(payload, dict):
            return None

        fs = payload.get("forecast_score")
        if isinstance(fs, (int, float)):
            v = float(fs)
            return v / 100.0 if v > 1.5 else v

        pts = payload.get("points")
        mx = payload.get("max_points")
        if isinstance(pts, (int, float)) and isinstance(mx, (int, float)) and mx:
            return float(pts) / float(mx)

        return None

    def _blend_components(sym):
        if not isinstance(sym, str) or not sym:
            return None

        c_val = util.get(sym)
        c_util = float(c_val) if isinstance(c_val, (int, float)) else None
        h1_util = _forecast_util(sym, H1)
        h5_util = _forecast_util(sym, H5)

        weights = {"c": 0.50, "h1": 0.25, "h5": 0.25}
        present = {"c": c_util, "h1": h1_util, "h5": h5_util}
        present = {k: v for k, v in present.items() if isinstance(v, (int, float))}
        denom = sum(weights[k] for k in present.keys())

        blended = (
            sum(weights[k] * float(v) for k, v in present.items()) / denom
            if denom > 0
            else None
        )

        return {
            "blended": blended,
            "c": c_util,
            "h1": h1_util,
            "h5": h5_util,
        }

    def _merge_comp(sym, comp):
        base = _blend_components(sym) or {}
        if isinstance(comp, dict):
            for k in ("blended", "c", "h1", "h5"):
                if comp.get(k) is not None:
                    base[k] = comp.get(k)
        return base if base else None

    def _comp_line(sym, comp):
        if not isinstance(sym, str) or not sym:
            return "-"
        if not isinstance(comp, dict):
            return sym
        return (
            f"{sym}  "
            f"(blend {_fmt(comp.get('blended'))} | "
            f"C {_fmt(comp.get('c'))} | "
            f"H1 {_fmt(comp.get('h1'))} | "
            f"H5 {_fmt(comp.get('h5'))})"
        )

    def _edge_by_h(row, horizon_days):
        edges = row.get("edges_by_h")
        if not isinstance(edges, dict):
            return None
        return _num(edges.get(str(horizon_days), edges.get(horizon_days)))

    def _short_reason(reason):
        s = str(reason or "").strip()
        if not s or s == "-":
            return "-"
        if s.startswith("disagreement_veto:edge(") and s.endswith(")<0"):
            hs = s[len("disagreement_veto:edge(") : -len(")<0")]
            hs = hs.replace(",", "")
            return f"e{hs}<0"
        mapping = {
            "below_floor": "flr",
            "below_delta": "dlt",
            "fallback_only": "fbk",
            "policy:max_precious_holdings": "pmx",
            "policy:block_gltr_component_overlap": "gco",
        }
        return mapping.get(s, s[:6])

    if not isinstance(rec_doc, dict):
        console.print(
            Panel(
                Text("recommendation cache unavailable", style="yellow"),
                title="Recommendation",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        return console.export_text(styles=True) + NL

    rec = rec_doc.get("recommendation")
    if not isinstance(rec, dict):
        rec = rec_doc if isinstance(rec_doc, dict) else {}

    d = rec.get("diagnostics") if isinstance(rec.get("diagnostics"), dict) else {}
    if not isinstance(d, dict):
        d = {}

    asof = (
        rec_doc.get("snapshot_asof")
        or rec_doc.get("asof")
        or rec_doc.get("generated_at")
        or "?"
    )
    action = str(rec.get("action") or "?").upper()
    reason = rec.get("reason") or "-"
    metric = d.get("decision_metric") or "-"
    weights = _fmt_pct_weights(d.get("utility_weights"))

    fp = rec_doc.get("snapshot_id") or rec_doc.get("computation_fingerprint") or "-"
    if isinstance(fp, str) and len(fp) > 12:
        fp = fp[:12]

    computed_at = rec_doc.get("computed_at") or rec_doc.get("generated_at") or "-"
    source_ts = (
        rec_doc.get("source_timestamps")
        if isinstance(rec_doc.get("source_timestamps"), dict)
        else {}
    )
    freshness = (
        rec_doc.get("freshness") if isinstance(rec_doc.get("freshness"), dict) else {}
    )

    snapshot_ts = (
        source_ts.get("snapshot_asof")
        or rec_doc.get("snapshot_asof")
        or rec_doc.get("asof")
        or "-"
    )
    positions_ts = (
        source_ts.get("positions_asof")
        or source_ts.get("positions")
        or rec_doc.get("positions_asof")
        or "-"
    )
    forecast_ts = (
        source_ts.get("forecast_source_asof")
        or source_ts.get("forecast_asof")
        or source_ts.get("forecast")
        or rec_doc.get("forecast_asof")
        or "-"
    )

    def _fmt_dt_et(v):
        if not v or v == "-":
            return "-"
        try:
            from datetime import datetime, timezone
            from zoneinfo import ZoneInfo

            s = str(v).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo("America/New_York")).strftime(
                "%Y-%m-%d %I:%M:%S %p %Z"
            )
        except Exception:
            return str(v)

    def _fmt_age(sec):
        try:
            sec = int(sec)
        except Exception:
            return "-"
        if sec < 60:
            return f"{sec}s"
        m, s = divmod(sec, 60)
        if m < 60:
            return f"{m}m {s:02d}s"
        h, m = divmod(m, 60)
        return f"{h}h {m:02d}m"

    rendered_now = _fmt_dt_et(
        __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat()
    )
    snapshot_display = _fmt_dt_et(snapshot_ts)
    positions_display = _fmt_dt_et(positions_ts)
    forecast_display = _fmt_dt_et(forecast_ts)
    computed_display = _fmt_dt_et(computed_at)

    p_fresh = (
        freshness.get("positions")
        if "positions" in freshness
        else freshness.get("positions_is_fresh")
    )
    f_fresh = (
        freshness.get("forecast")
        if "forecast" in freshness
        else freshness.get("forecast_is_fresh")
    )
    s_fresh = freshness.get("snapshot")
    if s_fresh is None:
        s_fresh = freshness.get("sectors_is_fresh")

    fresh_line = ", ".join(
        [
            f"p={'yes' if p_fresh else 'no'}" if p_fresh is not None else "p=-",
            f"f={'yes' if f_fresh else 'no'}" if f_fresh is not None else "f=-",
            f"s={'yes' if s_fresh else 'no'}" if s_fresh is not None else "s=-",
        ]
    )

    positions_age = (
        freshness.get("positions_age")
        if "positions_age" in freshness
        else freshness.get("positions_age_seconds")
    )
    forecast_age = (
        freshness.get("forecast_age")
        if "forecast_age" in freshness
        else freshness.get("forecast_age_seconds")
    )
    snapshot_age = freshness.get("snapshot_age")
    if snapshot_age is None:
        snapshot_age = freshness.get("sectors_age_seconds")

    skew_age = freshness.get("skew")
    if skew_age is None:
        skew_age = freshness.get("source_skew_seconds")

    age_line = f"{_fmt_age(positions_age)} / {_fmt_age(forecast_age)} / {_fmt_age(snapshot_age)}"
    skew_line = _fmt_age(skew_age)

    selected_pair = (
        d.get("selected_pair") if isinstance(d.get("selected_pair"), dict) else {}
    )
    best = selected_pair.get("to_symbol") or d.get("best_candidate")
    weakest = selected_pair.get("from_symbol") or d.get("weakest_held")

    held_components = d.get("held_components") or {}
    candidate_components = d.get("candidate_components") or {}
    best_components = _merge_comp(
        best,
        candidate_components if isinstance(candidate_components, dict) else None,
    )
    weakest_components = _merge_comp(
        weakest,
        held_components.get(weakest) if isinstance(held_components, dict) else None,
    )

    delta = _num(d.get("delta_utility"))
    thr = _num(d.get("threshold"))
    shortfall = (thr - delta) if (delta is not None and thr is not None) else None

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold cyan", no_wrap=True)
    summary.add_column(no_wrap=False)

    action_style = (
        "bold green"
        if action == "SWAP"
        else ("bold yellow" if action == "NOOP" else "bold white")
    )

    # BEGIN freshness fallback patch
    fb_source_ts, fb_freshness, fb_ages = _fallback_freshness_bundle(rec_doc, CACHE_DIR)

    if not isinstance(source_ts, dict):
        source_ts = {}
    source_ts = {
        "positions": source_ts.get("positions") or fb_source_ts.get("positions"),
        "forecast": source_ts.get("forecast") or fb_source_ts.get("forecast"),
        "snapshot": source_ts.get("snapshot") or fb_source_ts.get("snapshot"),
    }

    if not isinstance(freshness, dict):
        freshness = {}
    freshness = {
        "positions": freshness.get("positions")
        if isinstance(freshness.get("positions"), bool)
        else fb_freshness.get("positions"),
        "forecast": freshness.get("forecast")
        if isinstance(freshness.get("forecast"), bool)
        else fb_freshness.get("forecast"),
        "snapshot": freshness.get("snapshot")
        if isinstance(freshness.get("snapshot"), bool)
        else fb_freshness.get("snapshot"),
    }

    def _blankish(v):
        return v in (None, "", "-", "?")

    def _fresh_flag_fb(v):
        if v is None:
            return "-"
        return "yes" if bool(v) else "no"

    if "positions_display" in locals() and _blankish(positions_display):
        positions_display = source_ts.get("positions") or "-"
    if "forecast_display" in locals() and _blankish(forecast_display):
        forecast_display = source_ts.get("forecast") or "-"
    if "snapshot_display" in locals() and _blankish(snapshot_display):
        snapshot_display = source_ts.get("snapshot") or "-"
    if "computed_display" in locals() and _blankish(computed_display):
        computed_display = computed_at or "-"

    fresh_line = "p=%s, f=%s, s=%s" % (
        _fresh_flag_fb(freshness.get("positions")),
        _fresh_flag_fb(freshness.get("forecast")),
        _fresh_flag_fb(freshness.get("snapshot")),
    )

    age_line = "%s / %s / %s" % (
        fb_ages.get("positions") or "-",
        fb_ages.get("forecast") or "-",
        fb_ages.get("snapshot") or "-",
    )
    # END freshness fallback patch

    summary.add_row("rendered", str(rendered_now))
    summary.add_row("snapshot", str(snapshot_display))
    summary.add_row("positions", str(positions_display))
    summary.add_row("forecast", str(forecast_display))
    summary.add_row("computed", str(computed_display))
    summary.add_row("fresh", str(fresh_line))
    summary.add_row("age p/f/s", str(age_line))
    summary.add_row("skew", str(skew_line))
    summary.add_row("fp", str(fp))
    summary.add_row("asof", str(asof))
    summary.add_row("action", Text(action, style=action_style))
    summary.add_row("metric", str(metric))
    summary.add_row("weights", str(weights))
    summary.add_row("why", str(reason))
    summary.add_row("best", Text(_comp_line(best, best_components), style="bold green"))
    summary.add_row(
        "weakest", Text(_comp_line(weakest, weakest_components), style="bold yellow")
    )
    summary.add_row("delta", Text(_fmt(delta), style=_delta_style(delta, thr)))
    summary.add_row("threshold", Text(_fmt(thr), style="cyan"))
    if shortfall is not None:
        summary.add_row("shortfall", Text(_fmt(shortfall), style="yellow"))

    console.print(
        Panel(
            summary,
            title="Recommendation (cached)",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    # legacy per-position widgets suppressed; unified table shown above
    pair_rows = d.get("candidate_pairs") or []
    stale_positions = "stale_positions_cache" in str(reason)

    if stale_positions and (not isinstance(pair_rows, list) or not pair_rows):
        console.print(
            Panel(
                Text(
                    "Forecast candidate pairs are hidden because positions.v1.json is stale. Refresh positions to restore this panel.",
                    style="yellow",
                ),
                title="Forecast candidate pairs",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
    elif isinstance(pair_rows, list) and pair_rows:
        ptbl = Table(
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold magenta",
            expand=False,
        )
        ptbl.add_column("From", justify="left", no_wrap=True)
        ptbl.add_column("FromBl", justify="right", no_wrap=True)
        ptbl.add_column("To", justify="left", no_wrap=True)
        ptbl.add_column("ToBl", justify="right", no_wrap=True)
        ptbl.add_column("Robust", justify="right", no_wrap=True)
        ptbl.add_column("Weighted", justify="right", no_wrap=True)
        ptbl.add_column("Avg", justify="right", no_wrap=True)
        ptbl.add_column(f"H{H1}", justify="right", no_wrap=True)
        ptbl.add_column(f"H{H5}", justify="right", no_wrap=True)
        ptbl.add_column("Why", justify="left", no_wrap=True)

        def _pair_sort_key(r):
            veto_rank = 1 if bool(r.get("vetoed")) else 0
            robust_rank = -(_num(r.get("robust_edge")) or -999.0)
            weighted_rank = -(_num(r.get("weighted_robust_edge")) or -999.0)
            avg_rank = -(_num(r.get("avg_edge")) or -999.0)
            return (
                veto_rank,
                robust_rank,
                weighted_rank,
                avg_rank,
                str(r.get("from_symbol", "")),
                str(r.get("to_symbol", "")),
            )

        sel_from = str(selected_pair.get("from_symbol") or "")
        sel_to = str(selected_pair.get("to_symbol") or "")

        for row in sorted(pair_rows, key=_pair_sort_key):
            frm = str(row.get("from_symbol") or "")
            to = str(row.get("to_symbol") or "")
            frm_comp = _blend_components(frm) or {}
            to_comp = _blend_components(to) or {}
            vetoed = bool(row.get("vetoed"))
            from_structure = _structure_summary_for_symbol(
                fs_doc, frm, preferred_horizon=5
            )
            to_structure = _structure_summary_for_symbol(
                fs_doc, to, preferred_horizon=5
            )
            structure_why = _pair_reason_tag(from_structure, to_structure)
            veto_why = _short_reason(row.get("veto_reason"))
            why = structure_why or veto_why
            is_selected = frm == sel_from and to == sel_to

            frm_text = Text(
                frm + (" ★" if is_selected else ""),
                style="bold yellow" if is_selected else ("red" if vetoed else "white"),
            )
            to_text = Text(
                to + (" ★" if is_selected else ""),
                style="bold green" if is_selected else ("red" if vetoed else "white"),
            )

            ptbl.add_row(
                frm_text,
                Text(
                    _fmt(frm_comp.get("blended")),
                    style=_score_style(frm_comp.get("blended")),
                ),
                to_text,
                Text(
                    _fmt(to_comp.get("blended")),
                    style=_score_style(to_comp.get("blended")),
                ),
                Text(
                    _fmt(row.get("robust_edge")),
                    style=_delta_style(row.get("robust_edge"), thr),
                ),
                Text(
                    _fmt(row.get("weighted_robust_edge")),
                    style=_delta_style(row.get("weighted_robust_edge")),
                ),
                Text(
                    _fmt(row.get("avg_edge")),
                    style=_delta_style(row.get("avg_edge"), thr),
                ),
                Text(
                    _fmt(_edge_by_h(row, H1)),
                    style=_delta_style(_edge_by_h(row, H1), 0.0),
                ),
                Text(
                    _fmt(_edge_by_h(row, H5)),
                    style=_delta_style(_edge_by_h(row, H5), 0.0),
                ),
                Text(why, style="bold red" if vetoed else "white"),
            )

        console.print(
            Panel(
                ptbl,
                title="Forecast candidate pairs",
                border_style="magenta",
                box=box.ROUNDED,
            )
        )

    rows = d.get("candidate_rows") or []
    if isinstance(rows, list) and rows:
        tbl = Table(
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold cyan",
            expand=False,
        )
        tbl.add_column("Sym", justify="left", no_wrap=True)
        tbl.add_column("Blend", justify="right", no_wrap=True)
        tbl.add_column("C", justify="right", no_wrap=True)
        tbl.add_column("H1", justify="right", no_wrap=True)
        tbl.add_column("H5", justify="right", no_wrap=True)
        tbl.add_column("ΔBlend", justify="right", no_wrap=True)
        tbl.add_column("Thr", justify="right", no_wrap=True)
        tbl.add_column("Status", justify="left", no_wrap=True)

        def _sort_key(r):
            status_rank = 0 if str(r.get("status", "")).upper() == "READY" else 1
            delta_rank = -(_num(r.get("delta_blended")) or -999.0)
            blend_rank = -(_num(r.get("blended")) or -999.0)
            return (
                status_rank,
                delta_rank,
                blend_rank,
                str(r.get("symbol") or r.get("sym") or r.get("ticker") or ""),
            )

        for row in sorted(rows, key=_sort_key):
            sym = str(row.get("symbol") or row.get("sym") or row.get("ticker") or "")
            is_best = sym == best
            sym_text = Text(
                sym + (" ★" if is_best else ""),
                style="bold cyan" if is_best else "white",
            )
            tbl.add_row(
                sym_text,
                Text(_fmt(row.get("blended")), style=_score_style(row.get("blended"))),
                Text(_fmt(row.get("c")), style=_score_style(row.get("c"))),
                Text(_fmt(row.get("h1")), style=_score_style(row.get("h1"))),
                Text(_fmt(row.get("h5")), style=_score_style(row.get("h5"))),
                Text(
                    _fmt(row.get("delta_blended")),
                    style=_delta_style(row.get("delta_blended"), thr),
                ),
                Text(_fmt(row.get("threshold")), style="cyan"),
                Text(
                    str(row.get("status") or "-"),
                    style=_status_style(row.get("status")),
                ),
            )

        console.print(
            Panel(
                tbl,
                title="Forecast candidates",
                border_style="cyan",
                box=box.ROUNDED,
            )
        )

    return console.export_text(styles=True) + NL


def _backfill_sector_proxy_view_text(text):
    if not isinstance(text, str) or not text.strip():
        return text

    try:
        fs_doc = _forecast_scores_doc()
    except Exception:
        fs_doc = {}

    if not isinstance(fs_doc, dict):
        return text

    try:
        hs = fs_doc.get("horizons_trading_days") or [1, 5]
        H5 = int(hs[1] if len(hs) > 1 else 5)
    except Exception:
        H5 = 5

    row_re = re.compile(
        r"^(?P<lead>\s*│\s*│)"
        r"(?P<sym>[^│]+)│"
        r"(?P<b>[^│]+)│"
        r"(?P<c>[^│]+)│"
        r"(?P<h1>[^│]+)│"
        r"(?P<h5>[^│]+)│"
        r"(?P<sup>[^│]+)│"
        r"(?P<res>[^│]+)│"
        r"(?P<ov>[^│]+)│"
        r"(?P<state>[^│]+)│"
        r"(?P<stop>[^│]+)│"
        r"(?P<buy>[^│]+)"
        r"(?P<trail>│\s*│\s*)$"
    )

    def _fmt_num(v):
        if not isinstance(v, (int, float)):
            return "-"
        s = f"{float(v):.2f}".rstrip("0").rstrip(".")
        return s if s else "0"

    def _state_short(tags):
        if not isinstance(tags, list) or not tags:
            return "-"
        mp = {
            "near_damage_zone": "DMG",
            "overhead_heavy": "OH",
            "reclaim_ready": "RCL",
            "breakout_ready": "BRK",
        }
        out = []
        seen = set()
        for x in tags:
            k = str(x or "").strip()
            v = mp.get(k, k[:3].upper() if k else "")
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return ",".join(out) if out else "-"

    def _fit(s, width, *, right=False):
        s = str(s)
        if len(s) > width:
            s = s[:width]
        return s.rjust(width) if right else s.ljust(width)

    out = []
    in_proxy = False

    for line in text.splitlines():
        if "Sector Proxy View (derived from your holdings)" in line:
            in_proxy = True
            out.append(line)
            continue

        if in_proxy and "Derived sector proxies, not raw account positions." in line:
            in_proxy = False
            out.append(line)
            continue

        if in_proxy:
            m = row_re.match(line)
            if m:
                sym = str(m.group("sym") or "").strip()
                ss = {}
                try:
                    ss = _structure_summary_for_symbol(fs_doc, sym, horizon=H5) or {}
                except Exception:
                    ss = {}

                if isinstance(ss, dict) and ss:
                    sup = ss.get("support_cushion_atr")
                    res = ss.get("overhead_resistance_atr")
                    stop = ss.get("tactical_stop_candidate")
                    if stop is None:
                        stop = ss.get("catastrophic_stop_candidate")
                    buy = ss.get("stop_buy_candidate")
                    if buy is None:
                        buy = ss.get("breakout_trigger")
                    state = _state_short(ss.get("state_tags") or [])

                    line = "".join(
                        [
                            m.group("lead"),
                            m.group("sym"),
                            "│",
                            m.group("b"),
                            "│",
                            m.group("c"),
                            "│",
                            m.group("h1"),
                            "│",
                            m.group("h5"),
                            "│",
                            _fit(_fmt_num(sup), len(m.group("sup")), right=True),
                            "│",
                            _fit(_fmt_num(res), len(m.group("res")), right=True),
                            "│",
                            m.group("ov"),
                            "│",
                            _fit(state, len(m.group("state")), right=False),
                            "│",
                            _fit(_fmt_num(stop), len(m.group("stop")), right=True),
                            "│",
                            _fit(_fmt_num(buy), len(m.group("buy")), right=True),
                            m.group("trail"),
                        ]
                    )

        out.append(line)

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _compact_state_tags(value):
    raw = str(value or "").strip()
    if not raw or raw == "-":
        return "-"

    mp = {
        "near_damage_zone": "DMG",
        "overhead_heavy": "OH",
        "reclaim_ready": "RCL",
        "breakout_ready": "BRK",
    }

    out = []
    seen = set()
    for part in [x.strip() for x in raw.split(",") if str(x).strip()]:
        short = mp.get(part, part[:3].upper())
        if short not in seen:
            seen.add(short)
            out.append(short)

    return ",".join(out) if out else "-"


def _backfill_overview_state_compact_text(text):
    return text


def _extract_overview_row_map(text):
    import re

    if not isinstance(text, str) or not text.strip():
        return {}

    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)

    row_re = re.compile(
        r"^\s*│\s*(?P<sym>[A-Z]{2,5})\s+"
        r"(?P<blend>-|\d+%)\s+"
        r"(?P<c>-|\d+%)\s+"
        r"(?P<h1>-|\d+%)\s+"
        r"(?P<h5>-|\d+%)\s+"
        r"(?P<sup>-|\d+\.\d{2})\s+"
        r"(?P<res>-|\d+\.\d{2})\s+"
        r"(?P<state>.*?)\s+"
        r"(?P<stop>-|\d+\.\d{2})\s+"
        r"(?P<buy>-|\d+\.\d{2})\s*│\s*$"
    )

    out = {}
    for line in clean.splitlines():
        m = row_re.match(line.rstrip())
        if not m:
            continue
        d = m.groupdict()
        out[d["sym"]] = {
            "sym": d["sym"],
            "blend": d["blend"].strip(),
            "c": d["c"].strip(),
            "h1": d["h1"].strip(),
            "h5": d["h5"].strip(),
            "sup": d["sup"].strip(),
            "res": d["res"].strip(),
            "state": d["state"].strip(),
            "stop": d["stop"].strip(),
            "buy": d["buy"].strip(),
        }
    return out


def _backfill_sector_proxy_view_current_text(text, canonical_rows, inv_to_long):
    if not isinstance(text, str) or not text.strip():
        return text
    if not isinstance(canonical_rows, dict):
        canonical_rows = {}
    if not isinstance(inv_to_long, dict):
        inv_to_long = {}

    row_re = re.compile(
        r"^(?P<lead>\s*│\s*│)"
        r"(?P<sym>[^│]+)│"
        r"(?P<b>[^│]+)│"
        r"(?P<c>[^│]+)│"
        r"(?P<h1>[^│]+)│"
        r"(?P<h5>[^│]+)│"
        r"(?P<sup>[^│]+)│"
        r"(?P<res>[^│]+)│"
        r"(?P<ov>[^│]+)│"
        r"(?P<state>[^│]+)│"
        r"(?P<stop>[^│]+)│"
        r"(?P<buy>[^│]+)"
        r"(?P<trail>│\s*│\s*)$"
    )

    def _fit(s, width, *, right=False):
        s = str(s or "").strip()
        if len(s) > width:
            s = s[:width]
        return s.rjust(width) if right else s.ljust(width)

    def _compact_state(s):
        raw = str(s or "").strip()
        if not raw or raw == "-":
            return "-"
        mp = {
            "near_damage_zone": "DMG",
            "overhead_heavy": "OH",
            "reclaim_ready": "RCL",
            "breakout_ready": "BRK",
        }
        out = []
        seen = set()
        for part in [x.strip() for x in raw.split(",") if str(x).strip()]:
            short = mp.get(part, part[:3].upper())
            if short not in seen:
                seen.add(short)
                out.append(short)
        return ",".join(out) if out else raw

    out = []
    in_proxy = False

    for line in text.splitlines():
        if "Sector Proxy View (derived from your holdings)" in line:
            in_proxy = True
            out.append(line)
            continue

        if in_proxy and "Derived sector proxies, not raw account positions." in line:
            in_proxy = False
            out.append(line)
            continue

        if in_proxy:
            m = row_re.match(line)
            if m:
                held_sym = str(m.group("sym") or "").strip().upper()
                proxy_sym = _proxy_for_symbol(held_sym, inv_to_long)
                src = canonical_rows.get(proxy_sym)

                if isinstance(src, dict) and src:
                    line = "".join(
                        [
                            m.group("lead"),
                            m.group("sym"),
                            "│",
                            _fit(src.get("blend", "-"), len(m.group("b")), right=True),
                            "│",
                            _fit(src.get("c", "-"), len(m.group("c")), right=True),
                            "│",
                            _fit(src.get("h1", "-"), len(m.group("h1")), right=True),
                            "│",
                            _fit(src.get("h5", "-"), len(m.group("h5")), right=True),
                            "│",
                            _fit(src.get("sup", "-"), len(m.group("sup")), right=True),
                            "│",
                            _fit(src.get("res", "-"), len(m.group("res")), right=True),
                            "│",
                            _fit(m.group("ov"), len(m.group("ov")), right=False),
                            "│",
                            _fit(
                                _compact_state(src.get("state", "-")),
                                min(len(m.group("state")), 11),
                                right=False,
                            ),
                            "│",
                            _fit(
                                src.get("stop", "-"), len(m.group("stop")), right=True
                            ),
                            "│",
                            _fit(src.get("buy", "-"), len(m.group("buy")), right=True),
                            m.group("trail"),
                        ]
                    )

        out.append(line)

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _file_mtime_iso(path):
    try:
        from pathlib import Path
        from datetime import datetime, timezone

        ts = Path(path).stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except Exception:
        return None


def _parse_iso_utc_local(s):
    try:
        from datetime import datetime, timezone

        s = str(s or "").strip()
        if not s:
            return None
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fmt_age_short_local(delta_seconds):
    try:
        n = int(max(0, float(delta_seconds)))
    except Exception:
        return "-"
    if n < 60:
        return f"{n}s"
    if n < 3600:
        return f"{n // 60}m"
    if n < 86400:
        return f"{n // 3600}h"
    return f"{n // 86400}d"


def _fresh_bool_from_age_local(delta_seconds, max_age_seconds):
    try:
        return float(delta_seconds) <= float(max_age_seconds)
    except Exception:
        return None


def _fmt_ts_et(value, *, default="n/a"):
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        if value in (None, "", "-"):
            return default

        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        else:
            dt = _parse_iso_utc_local(value)
            if dt is None:
                return default if value in (None, "", "-") else str(value)

        return dt.astimezone(ZoneInfo("America/New_York")).strftime(
            "%Y-%m-%d %I:%M:%S %p ET"
        )
    except Exception:
        return default if value in (None, "", "-") else str(value)


def _banner_now_et():
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        return "ET"


def _backfill_header_time_text(text):
    if not isinstance(text, str) or not text.strip():
        return text

    stamp = _banner_now_et()
    out = []

    for line in text.splitlines():
        if (
            "Market Health – Sector Union" in line
            and "•" in line
            and line.startswith("╭")
            and line.endswith("╮")
        ):
            inner_width = max(10, len(line) - 2)
            label = f" Market Health – Sector Union  •  {stamp} "
            if len(label) > inner_width:
                label = label[:inner_width]
            pad_total = inner_width - len(label)
            left = pad_total // 2
            right = pad_total - left
            line = "╭" + ("─" * left) + label + ("─" * right) + "╮"
        out.append(line)

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _build_display_freshness_bundle(rec_doc, cache_dir):
    from datetime import datetime, timezone

    rec_doc = rec_doc if isinstance(rec_doc, dict) else {}

    # Normalize fallback return shape.
    fb = (
        _fallback_freshness_bundle(rec_doc, cache_dir)
        if "_fallback_freshness_bundle" in globals()
        else ({}, {}, {})
    )
    if isinstance(fb, tuple) and len(fb) == 3:
        fb_source_ts, fb_freshness, fb_ages = fb
    elif isinstance(fb, dict):
        fb_source_ts = fb.get("source_timestamps") or {}
        fb_freshness = fb.get("freshness") or {}
        fb_ages = fb.get("ages") or {}
    else:
        fb_source_ts, fb_freshness, fb_ages = {}, {}, {}

    fb_source_ts = fb_source_ts if isinstance(fb_source_ts, dict) else {}
    fb_freshness = fb_freshness if isinstance(fb_freshness, dict) else {}
    fb_ages = fb_ages if isinstance(fb_ages, dict) else {}

    real_source_ts = rec_doc.get("source_timestamps")
    real_freshness = rec_doc.get("freshness")

    real_source_ts = real_source_ts if isinstance(real_source_ts, dict) else {}
    real_freshness = real_freshness if isinstance(real_freshness, dict) else {}

    have_real_source_ts = bool(real_source_ts)
    have_real_freshness = bool(real_freshness)

    # Old behavior only when nothing real exists upstream.
    if not have_real_source_ts and not have_real_freshness:
        return {
            "source_timestamps": fb_source_ts,
            "freshness": fb_freshness,
            "ages": fb_ages,
            "derived": True,
        }

    source_timestamps = {
        "positions": real_source_ts.get("positions") or fb_source_ts.get("positions"),
        "forecast": real_source_ts.get("forecast") or fb_source_ts.get("forecast"),
        "snapshot": real_source_ts.get("snapshot") or fb_source_ts.get("snapshot"),
    }

    # Preserve upstream truth exactly; fill only missing keys from fallback.
    freshness = {
        "positions": real_freshness["positions"]
        if "positions" in real_freshness
        else fb_freshness.get("positions"),
        "forecast": real_freshness["forecast"]
        if "forecast" in real_freshness
        else fb_freshness.get("forecast"),
        "snapshot": real_freshness["snapshot"]
        if "snapshot" in real_freshness
        else fb_freshness.get("snapshot"),
    }

    now = datetime.now(timezone.utc)

    def _age_for(ts_value):
        dt = _parse_iso_utc(ts_value)
        if dt is None:
            return None
        try:
            return (now - dt).total_seconds()
        except Exception:
            return None

    ages = {
        "positions": _age_for(source_timestamps.get("positions")),
        "forecast": _age_for(source_timestamps.get("forecast")),
        "snapshot": _age_for(source_timestamps.get("snapshot")),
    }

    return {
        "source_timestamps": source_timestamps,
        "freshness": freshness,
        "ages": ages,
        "derived": False,
    }


def _backfill_recommendation_panel_text(text, rec_doc, cache_dir):
    if not isinstance(text, str) or not text.strip():
        return text

    rec_doc = rec_doc if isinstance(rec_doc, dict) else {}
    bundle = _build_display_freshness_bundle(rec_doc, cache_dir)
    bundle = bundle if isinstance(bundle, dict) else {}

    source_ts = (
        bundle.get("source_timestamps")
        if isinstance(bundle.get("source_timestamps"), dict)
        else {}
    )
    freshness = (
        bundle.get("freshness") if isinstance(bundle.get("freshness"), dict) else {}
    )
    ages = bundle.get("ages") if isinstance(bundle.get("ages"), dict) else {}
    derived = bool(bundle.get("derived"))

    rec = rec_doc.get("recommendation")
    if not isinstance(rec, dict):
        rec = {}

    diag = rec.get("diagnostics")
    if not isinstance(diag, dict):
        diag = {}

    def _yn(v):
        if v is True:
            return "yes"
        if v is False:
            return "no"
        return "?"

    def _short_json(v, default="n/a"):
        import json

        if v in (None, "", "-", {}, []):
            return default
        if isinstance(v, (dict, list, tuple)):
            try:
                return json.dumps(v, sort_keys=True, separators=(",", ":"))
            except Exception:
                return str(v)
        return str(v)

    rendered_val = _banner_now_et()
    snapshot_val = _fmt_ts_et(
        rec_doc.get("snapshot_asof")
        or rec_doc.get("asof")
        or source_ts.get("snapshot")
        or source_ts.get("positions")
    )
    positions_val = _fmt_ts_et(source_ts.get("positions"))
    forecast_val = _fmt_ts_et(source_ts.get("forecast"))
    computed_val = _fmt_ts_et(rec_doc.get("computed_at") or rec_doc.get("generated_at"))

    fresh_core = "p={p}, f={f}, s={s}".format(
        p=_yn(freshness.get("positions")),
        f=_yn(freshness.get("forecast")),
        s=_yn(freshness.get("snapshot")),
    )
    fresh_val = ("derived " + fresh_core) if derived else fresh_core

    age_val = "{p} / {f} / {s}".format(
        p=_fmt_age_short_local(ages.get("positions")),
        f=_fmt_age_short_local(ages.get("forecast")),
        s=_fmt_age_short_local(ages.get("snapshot")),
    )

    replacements = {
        "rendered": rendered_val,
        "snapshot": snapshot_val,
        "positions": positions_val,
        "forecast": forecast_val,
        "computed": computed_val,
        "fresh": fresh_val,
        "age p/f/s": age_val,
        "skew": _short_json(
            diag.get("skew")
            or diag.get("snapshot_skew")
            or rec_doc.get("skew")
            or rec_doc.get("source_skew"),
            default="n/a",
        ),
        "fp": _short_json(
            rec_doc.get("snapshot_id")
            or rec_doc.get("computation_fingerprint")
            or diag.get("fingerprint"),
            default="n/a",
        ),
        "weights": _short_json(
            diag.get("utility_weights") or rec.get("utility_weights"),
            default="n/a",
        ),
    }

    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    in_panel = False
    out = []

    for line in text.splitlines():
        plain = ansi_re.sub("", line)

        if "Recommendation (cached)" in plain:
            in_panel = True
            out.append(line)
            continue

        if in_panel and plain.startswith("╰"):
            in_panel = False
            out.append(line)
            continue

        if in_panel and plain.startswith("│"):
            width = max(0, len(plain) - 2)
            replaced = False
            for label, value in replacements.items():
                if plain.strip().startswith("│ " + label):
                    content = f" {label:<10} {value}"
                    if len(content) > width:
                        content = content[:width]
                    out.append("│" + content.ljust(width) + "│")
                    replaced = True
                    break
            if replaced:
                continue

        out.append(line)

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main() -> int:
    user_args = sys.argv[1:]

    rec_doc = read_json(REC_PATH)

    core = run_core_ui(user_args)
    core = _backfill_header_time_text(core)
    core = _backfill_sector_proxy_view_text(core)
    prefix, detail_blocks, _detail_order = split_core_output(core)
    prefix = _strip_prefix_sections(prefix)
    order, util = parse_overview_totals(prefix)

    inv_syms = []
    # --- Inverse ETF augmentation (map-only; no score overrides) ---
    #     try:
    #         if inv_syms:
    #             rec_doc_local = read_json(REC_PATH)
    #             inputs = rec_doc_local.get("inputs") if isinstance(rec_doc_local, dict) else None
    #             period = str(inputs.get("period")) if isinstance(inputs, dict) and inputs.get("period") else "6mo"
    #             interval = str(inputs.get("interval")) if isinstance(inputs, dict) and inputs.get("interval") else "1d"
    #
    #             inv_rows = compute_scores(sectors=inv_syms, period=period, interval=interval)
    #
    #             def _row_util(row):
    #                 total = 0
    #                 maxp = 0
    #                 cats = row.get("categories", {})
    #                 if isinstance(cats, dict):
    #                     for cat in cats.values():
    #                         checks = cat.get("checks") if isinstance(cat, dict) else None
    #                         if isinstance(checks, list):
    #                             for chk in checks:
    #                                 sc = chk.get("score") if isinstance(chk, dict) else None
    #                                 if isinstance(sc, int):
    #                                     total += sc
    #                                     maxp += 2
    #                 return (total / maxp) if maxp else None
    #
    #             for r in inv_rows:
    #                 sym = str(r.get("symbol") or "").upper().strip()
    #                 u = _row_util(r)
    #                 if sym and (u is not None):
    #                     util[sym] = float(u)
    #     except Exception:
    #         pass
    # --- end inverse augmentation ---

    # Expanded universe order (cache-first): prefer UI snapshot sectors (includes inverses)

    order_all = list(order)

    try:
        ui_path = Path(
            os.path.expanduser(
                os.environ.get(
                    "JERBOA_UI_JSON", "~/.cache/jerboa/market_health.ui.v1.json"
                )
            )
        ).expanduser()

        snap = read_json(ui_path)

        if (
            isinstance(snap, dict)
            and isinstance(snap.get("data"), dict)
            and isinstance(snap["data"].get("sectors"), list)
        ):
            order_all, util = _snapshot_order_util(snap)

            # keep inv_syms consistent for downstream sections that gate on it

            inv_syms = [
                x for x in order_all if isinstance(x, str) and not x.startswith("XL")
            ]

        else:
            for x in inv_syms:
                if x not in order_all:
                    order_all.append(x)

    except Exception:
        for x in inv_syms:
            if x not in order_all:
                order_all.append(x)

    blocked_syms = {"XLV", "CSWC"}
    order_all = [s for s in order_all if str(s).upper().strip() not in blocked_syms]
    util = {
        str(k).upper().strip(): v
        for k, v in util.items()
        if str(k).upper().strip() not in blocked_syms
    }
    order = list(order_all)

    fs_doc = _forecast_scores_doc()
    try:
        _hs = fs_doc.get("horizons_trading_days") if isinstance(fs_doc, dict) else None
        _h5 = int(_hs[1]) if isinstance(_hs, (list, tuple)) and len(_hs) > 1 else 5
    except Exception:
        _h5 = 5

    def _merge_live_structure(dst, ss):
        if not isinstance(dst, dict) or not isinstance(ss, dict) or not ss:
            return

        tags = list(ss.get("state_tags") or [])
        stop = ss.get("tactical_stop_candidate")
        if stop is None:
            stop = ss.get("catastrophic_stop_candidate")
        buy = ss.get("stop_buy_candidate")
        if buy is None:
            buy = ss.get("breakout_trigger")

        sup = ss.get("support_cushion_atr")
        res = ss.get("overhead_resistance_atr")

        # canonical keys
        dst["support_cushion_atr"] = sup
        dst["overhead_resistance_atr"] = res
        dst["state_tags"] = tags
        dst["catastrophic_stop_candidate"] = ss.get("catastrophic_stop_candidate")
        dst["catastrophic_stop"] = ss.get("catastrophic_stop_candidate")
        dst["tactical_stop_candidate"] = stop
        dst["stop_buy_candidate"] = buy
        dst["stop_buy"] = buy
        dst["breakout_trigger"] = ss.get("breakout_trigger")

        # renderer-friendly aliases for legacy / compact UI paths
        dst["sup_atr"] = sup
        dst["res_atr"] = res
        dst["stop"] = stop
        dst["buy"] = buy
        dst["state"] = ",".join(tags) if tags else "-"

    for _sym in order_all:
        _row = util.get(_sym)
        _ss = _structure_summary_for_symbol(fs_doc, _sym, horizon=_h5)
        if isinstance(_row, dict) and _ss:
            _merge_live_structure(_row, _ss)

    def _detail_block_sym(_blk):
        if not isinstance(_blk, dict):
            return ""
        _sym = (
            _blk.get("symbol")
            or _blk.get("sym")
            or _blk.get("src")
            or _blk.get("source_symbol")
        )
        if not _sym:
            _ui = _blk.get("ui_row")
            if isinstance(_ui, dict):
                _sym = _ui.get("symbol") or _ui.get("sym") or _ui.get("src")
        return str(_sym or "").upper().strip()

    detail_blocks = [
        _blk for _blk in detail_blocks if _detail_block_sym(_blk) not in {"CSWC"}
    ]

    for _blk in detail_blocks:
        if not isinstance(_blk, dict):
            continue

        _sym = (
            _blk.get("symbol")
            or _blk.get("sym")
            or _blk.get("src")
            or _blk.get("source_symbol")
        )

        if not _sym:
            _ui = _blk.get("ui_row")
            if isinstance(_ui, dict):
                _sym = _ui.get("symbol") or _ui.get("sym") or _ui.get("src")

        if not _sym:
            continue

        _ss = _structure_summary_for_symbol(fs_doc, _sym, horizon=_h5)
        if not _ss:
            continue

        _merge_live_structure(_blk, _ss)

        for _k in ("ui_row", "composite", "score_components", "comp", "payload"):
            _child = _blk.get(_k)
            if isinstance(_child, dict):
                _merge_live_structure(_child, _ss)

    fs_doc = _forecast_scores_doc()
    try:
        _hs = fs_doc.get("horizons_trading_days") if isinstance(fs_doc, dict) else None
        _h5 = int(_hs[1]) if isinstance(_hs, (list, tuple)) and len(_hs) > 1 else 5
    except Exception:
        _h5 = 5

    def _resolved_fs_symbol(_sym):
        _s = str(_sym or "").upper().strip()
        _scores = fs_doc.get("scores") or {}
        if _s in _scores:
            return _s
        _mapped = inv_to_long.get(_s) if isinstance(inv_to_long, dict) else None
        if _mapped:
            _m = str(_mapped).upper().strip()
            if _m in _scores:
                return _m
        return _s

    def _merge_live_structure(dst, ss):
        if not isinstance(dst, dict) or not isinstance(ss, dict) or not ss:
            return

        tags = list(ss.get("state_tags") or [])
        stop = ss.get("tactical_stop_candidate")
        if stop is None:
            stop = ss.get("catastrophic_stop_candidate")
        buy = ss.get("stop_buy_candidate")
        if buy is None:
            buy = ss.get("breakout_trigger")

        sup = ss.get("support_cushion_atr")
        res = ss.get("overhead_resistance_atr")

        dst["structure_summary"] = dict(ss)
        dst["support_cushion_atr"] = sup
        dst["overhead_resistance_atr"] = res
        dst["state_tags"] = tags
        dst["catastrophic_stop_candidate"] = ss.get("catastrophic_stop_candidate")
        dst["catastrophic_stop"] = ss.get("catastrophic_stop_candidate")
        dst["tactical_stop_candidate"] = stop
        dst["tactical_stop"] = stop
        dst["stop_buy_candidate"] = buy
        dst["stop_buy"] = buy
        dst["breakout_trigger"] = ss.get("breakout_trigger")

        # legacy / renderer-friendly aliases
        dst["sup_atr"] = sup
        dst["res_atr"] = res
        dst["state"] = ",".join(tags) if tags else "-"
        dst["stop"] = stop
        dst["buy"] = buy

    def _maybe_copy_proxy_scores(dst, proxy_row):
        if not isinstance(dst, dict) or not isinstance(proxy_row, dict):
            return
        for k in (
            "blend",
            "b",
            "current",
            "c",
            "h1",
            "h5",
            "current_health",
            "current_score",
            "forecast_h1",
            "forecast_h5",
            "score_h1",
            "score_h5",
        ):
            if dst.get(k) in (None, "", "-") and proxy_row.get(k) not in (
                None,
                "",
                "-",
            ):
                dst[k] = proxy_row.get(k)

    for _sym, _row in list(util.items()):
        if not isinstance(_row, dict):
            continue
        _proxy = _resolved_fs_symbol(_sym)
        if _proxy != _sym and isinstance(util.get(_proxy), dict):
            _maybe_copy_proxy_scores(_row, util.get(_proxy))
        _ss = _structure_summary_for_symbol(fs_doc, _proxy, horizon=_h5)
        _merge_live_structure(_row, _ss)

    for _blk in detail_blocks:
        if not isinstance(_blk, dict):
            continue

        _sym = (
            _blk.get("symbol")
            or _blk.get("sym")
            or _blk.get("src")
            or _blk.get("source_symbol")
        )

        if not _sym:
            _ui = _blk.get("ui_row")
            if isinstance(_ui, dict):
                _sym = _ui.get("symbol") or _ui.get("sym") or _ui.get("src")

        if not _sym:
            continue

        _proxy = _resolved_fs_symbol(_sym)

        if _proxy != _sym and isinstance(util.get(_proxy), dict):
            _maybe_copy_proxy_scores(_blk, util.get(_proxy))

        _ss = _structure_summary_for_symbol(fs_doc, _proxy, horizon=_h5)
        _merge_live_structure(_blk, _ss)

        for _k in ("ui_row", "composite", "score_components", "comp", "payload"):
            _child = _blk.get(_k)
            if isinstance(_child, dict):
                if _proxy != _sym and isinstance(util.get(_proxy), dict):
                    _maybe_copy_proxy_scores(_child, util.get(_proxy))
                _merge_live_structure(_child, _ss)

    held_syms = pick_positions(detail_blocks, rec_doc)
    # Snapshot-first fallback (cache-only, consistent payload):
    # If held_syms is empty, derive sector ETF holdings from the cached UI contract snapshot.
    if not held_syms:
        try:
            ui_path = Path(
                os.path.expanduser(
                    os.environ.get(
                        "JERBOA_UI_JSON", "~/.cache/jerboa/market_health.ui.v1.json"
                    )
                )
            ).expanduser()
            snap = read_json(ui_path)
            data = snap.get("data") or {}
            pos = data.get("positions")
            if isinstance(pos, dict):
                rows = pos.get("positions") or []
                for r in rows:
                    if isinstance(r, dict) and isinstance(r.get("symbol"), str):
                        sym = r["symbol"].strip().upper()
                        if sym.startswith("XL") and len(sym) <= 5:
                            held_syms.append(sym)
                held_syms = sorted(set(held_syms))
        except Exception:
            pass

    # 1) Overview
    sys.stdout.write(strip_core_overview(prefix).rstrip() + "\n\n")
    overview_text_raw = render_overview_triscore(order_all, util, [])
    canonical_overview_rows = _extract_overview_row_map(overview_text_raw)
    overview_text = _backfill_overview_state_compact_text(overview_text_raw)
    sys.stdout.write(overview_text + "\n")
    # 3) Details for positions (TRI-SCORE ASCII prototype)

    #             # --- Snapshot widgets (cache-only) ---
    #     try:
    #         ui_path = Path(os.path.expanduser(os.environ.get("JERBOA_UI_JSON", "~/.cache/jerboa/market_health.ui.v1.json"))).expanduser()
    #         snap = read_json(ui_path)
    #         if isinstance(snap, dict) and isinstance(snap.get("data"), dict) and isinstance(snap["data"].get("sectors"), list):
    #             snap_order, snap_util = _snapshot_order_util(snap)

    #             lines2 = []
    #             lines2.append(c("Overview (totals-only from snapshot)", CYAN))
    #             lines2.append(f"{'Sym':<6}  {'Total':>12}")
    #             lines2.append("-" * 22)
    #             for sym in snap_order:
    #                 u = snap_util.get(sym)
    #                 if not isinstance(u, float):
    #                     continue
    #                 pct = int(round(u * 100))
    #                 letter, col = grade_letter(pct)
    #                 lines2.append(f"{sym:<6}  {pct:>3}% {c(letter, col)}")
    #             sys.stdout.write("\n".join(lines2) + "\n\n")

    #             sys.stdout.write(render_pi_grid(snap_order, snap_util) + "\n")
    #     except Exception:
    #         pass
    #     # --- end snapshot widgets ---

    sys.stdout.write(
        c("=" * 30 + " Details (your positions) " + "=" * 30, CYAN) + chr(10)
    )

    if not held_syms:
        sys.stdout.write(
            c(
                "No positions detected yet (no positions cache; fallback held_scored also missing)."
                + chr(10),
                YELLOW,
            )
        )

        sys.stdout.write(
            "If you expect Schwab/TOS positions here, ensure positions refresh actually produces a positions cache file."
            + chr(10)
            + chr(10)
        )

    else:
        try:
            from market_health.ui_triscore_ascii import render_positions_triscore_ascii

            from rich.console import Console

            console = Console()

            raw_panel = None
            try:
                from market_health.ui_positions_compact_rich import (
                    _render_actual_holdings_panel,
                )

                pos_doc = read_json(CACHE_DIR / "positions.v1.json")
                raw_panel = _render_actual_holdings_panel(pos_doc)
            except Exception:
                raw_panel = None

            if raw_panel is not None:
                console.print(raw_panel)
                console.print()

            compact_panel = None
            try:
                from market_health.ui_positions_unified_rich import (
                    render_positions_unified_panel,
                )

                compact_panel = render_positions_unified_panel()
            except Exception:
                compact_panel = None

            if compact_panel is not None:
                import io

                buf_console = Console(
                    record=True,
                    force_terminal=False,
                    color_system=None,
                    width=max(160, int(os.environ.get("COLUMNS", "160"))),
                    file=io.StringIO(),
                )
                buf_console.print(compact_panel)
                compact_text = buf_console.export_text()
                compact_text = _backfill_sector_proxy_view_text(compact_text)
                inv_to_long_local = _load_inverse_map_from_cache()

                compact_text = _backfill_sector_proxy_view_current_text(
                    compact_text,
                    canonical_overview_rows,
                    inv_to_long_local,
                )
                sys.stdout.write(
                    compact_text
                    if compact_text.endswith(chr(10))
                    else compact_text + chr(10)
                )
                sys.stdout.write(chr(10))
            else:
                sys.stdout.write(render_positions_triscore_ascii() + chr(10))
        except Exception as e:
            sys.stdout.write(
                c("Tri-Score ASCII unavailable: %s" % (e,) + chr(10) + chr(10), YELLOW)
            )

            # legacy per-position detail blocks suppressed; unified table shown above

    # 4) Recommendation + READY/BLOCKED table
    reco_text = render_reco(order, util, rec_doc, held_syms)
    reco_text = _backfill_recommendation_panel_text(reco_text, rec_doc, CACHE_DIR)
    sys.stdout.write(reco_text)
    return 0


if __name__ == "__main__":
    import argparse
    import sys
    import time

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument(
        "--watch",
        type=int,
        default=0,
        help="Auto-refresh every N seconds (e.g., 900 for 15 minutes)",
    )
    args, rest = ap.parse_known_args()
    sys.argv = [sys.argv[0]] + rest

    if args.watch and args.watch > 0:
        try:
            while True:
                print("\033[2J\033[H", end="")
                main()
                time.sleep(max(1, args.watch))
        except KeyboardInterrupt:
            pass
    else:
        raise SystemExit(main())
