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


def render_overview_triscore(order, held_syms):
    NL = chr(10)
    cache = Path.home() / ".cache" / "jerboa"
    ui_p = cache / "market_health.ui.v1.json"
    fs_doc = _forecast_scores_doc()
    fs_p = cache / "forecast_scores.v1.json"

    def _jload(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

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
        return int(round((pts / mx) * 100)) if mx else None

    def _forecast_pct(scores, sym, horizon):
        if not isinstance(scores, dict):
            return None
        by_h = scores.get(sym)
        if not isinstance(by_h, dict):
            return None
        node = by_h.get(str(horizon), by_h.get(horizon))
        if not isinstance(node, dict):
            return None

        fs = node.get("forecast_score")
        if isinstance(fs, (int, float)):
            val = float(fs)
            return int(round(val * 100)) if val <= 1.5 else int(round(val))

        pts = node.get("points")
        mx = node.get("max_points")
        if isinstance(pts, (int, float)) and isinstance(mx, (int, float)) and mx:
            return int(round((float(pts) / float(mx)) * 100))
        return None

    def _fmt_pct(v):
        if isinstance(v, (int, float)):
            return f"{int(v):>3d}%"
        return "  - "

    def _fmt_delta(v):
        if isinstance(v, (int, float)):
            return f"{int(v):+4d}"
        return "   -"

    ui = _jload(ui_p)
    fs = _jload(fs_p)

    raw_sectors = (
        ((ui.get("data") or {}).get("sectors") or {}) if isinstance(ui, dict) else {}
    )
    sector_map = {}
    if isinstance(raw_sectors, dict):
        for k, v in raw_sectors.items():
            sym = str(k).strip().upper()
            if sym and isinstance(v, dict):
                sector_map[sym] = v
    elif isinstance(raw_sectors, list):
        for row in raw_sectors:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                sector_map[sym] = row

    raw_scores = (fs.get("scores") or {}) if isinstance(fs, dict) else {}
    scores = raw_scores if isinstance(raw_scores, dict) else {}
    held_set = {str(s).strip().upper() for s in (held_syms or []) if str(s).strip()}

    syms = []
    for s in order or []:
        sym = str(s).strip().upper()
        if sym and sym not in syms:
            syms.append(sym)
    if not syms and isinstance(sector_map, dict):
        syms = sorted(sector_map.keys())

    import io
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    def _pct_style(v):
        if v is None:
            return "dim"
        if v >= 60:
            return "bold green"
        if v >= 40:
            return "bold yellow"
        return "bold red"

    def _delta_style(v):
        if v is None:
            return "dim"
        if v > 0:
            return "bold green"
        if v < 0:
            return "bold red"
        return "dim"

    console = Console(
        record=True,
        force_terminal=True,
        color_system="truecolor",
        width=88,
        file=io.StringIO(),
    )

    table = Table(
        box=box.ROUNDED,
        expand=True,
        header_style="bold cyan",
        border_style="bright_blue",
        pad_edge=False,
        padding=(0, 1),
        show_lines=True,
        row_styles=["none", "on rgb(20,24,28)"],
    )
    table.add_column("Sym", style="bold white", no_wrap=True, width=7)
    table.add_column("Blend", justify="right", no_wrap=True, width=5)
    table.add_column("C", justify="right", no_wrap=True, width=4)
    table.add_column("H1", justify="right", no_wrap=True, width=4)
    table.add_column("H5", justify="right", no_wrap=True, width=4)
    table.add_column("SupATR", justify="right", no_wrap=True, width=6)
    table.add_column("ResATR", justify="right", no_wrap=True, width=6)
    table.add_column("State", justify="left", no_wrap=True, width=5)
    table.add_column("Δ1", justify="right", no_wrap=True, width=4)
    table.add_column("Δ5", justify="right", no_wrap=True, width=4)

    rows = []
    for sym in syms:
        row = sector_map.get(sym)
        if not isinstance(row, dict):
            continue

        c_pct = _sum_cat_pct(row)
        h1_pct = _forecast_pct(scores, sym, 1)
        h5_pct = _forecast_pct(scores, sym, 5)

        d1 = None if c_pct is None or h1_pct is None else (h1_pct - c_pct)
        d5 = None if c_pct is None or h5_pct is None else (h5_pct - c_pct)

        structure = _structure_summary_for_symbol(fs_doc, sym, preferred_horizon=5)
        sup_atr = _fmt_atr_short(structure.get("support_cushion_atr"))
        res_atr = _fmt_atr_short(structure.get("overhead_resistance_atr"))
        state_txt = _state_tag_short(structure.get("state_tags"))

        blend_pct = None
        if c_pct is not None and h1_pct is not None and h5_pct is not None:
            blend_pct = (0.50 * c_pct) + (0.25 * h1_pct) + (0.25 * h5_pct)

        sym_txt = (
            f"[bold white]{sym}[/][bold magenta]•[/]"
            if sym in held_set
            else f"[bold white]{sym}[/]"
        )

        blend_txt = f"[{_pct_style(blend_pct)}]{_fmt_pct(blend_pct)}[/]"
        c_txt = f"[{_pct_style(c_pct)}]{_fmt_pct(c_pct)}[/]"
        h1_txt = f"[{_pct_style(h1_pct)}]{_fmt_pct(h1_pct)}[/]"
        h5_txt = f"[{_pct_style(h5_pct)}]{_fmt_pct(h5_pct)}[/]"
        d1_txt = f"[{_delta_style(d1)}]{_fmt_delta(d1)}[/]"
        d5_txt = f"[{_delta_style(d5)}]{_fmt_delta(d5)}[/]"

        rows.append(
            {
                "sym": sym,
                "blend": blend_pct,
                "sym_txt": sym_txt,
                "blend_txt": blend_txt,
                "c_txt": c_txt,
                "h1_txt": h1_txt,
                "h5_txt": h5_txt,
                "sup_atr": sup_atr,
                "res_atr": res_atr,
                "state_txt": state_txt,
                "d1_txt": d1_txt,
                "d5_txt": d5_txt,
            }
        )

    rows.sort(
        key=lambda r: (
            r["blend"] is None,
            -(r["blend"] if r["blend"] is not None else -1.0),
            r["sym"],
        )
    )

    for r in rows:
        table.add_row(
            r["sym_txt"],
            r["blend_txt"],
            r["c_txt"],
            r["h1_txt"],
            r["h5_txt"],
            r["sup_atr"],
            r["res_atr"],
            r["state_txt"],
            r["d1_txt"],
            r["d5_txt"],
        )

    console.print()
    console.print(
        Panel(
            table,
            title="[bold white]Overview (expanded universe, compact tri-score)[/] [bold magenta]• held[/]",
            border_style="bright_blue",
            padding=(0, 1),
        )
    )

    return console.export_text(styles=True) + NL


def _forecast_scores_doc() -> dict[str, Any]:
    doc = read_json(CACHE_DIR / "forecast_scores.v1.json")
    return doc if isinstance(doc, dict) else {}


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
    scores_doc: dict[str, Any], sym: str, preferred_horizon: int = 5
) -> dict[str, Any]:
    payload = _forecast_payload_for_symbol(scores_doc, sym, preferred_horizon)
    ss = payload.get("structure_summary")
    return ss if isinstance(ss, dict) else {}


def _fmt_atr_short(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return "-"
    return f"{float(v):.2f}"


def _state_tag_short(tags: Any) -> str:
    if not isinstance(tags, list):
        return "-"
    tag_set = {str(x) for x in tags}
    if "breakout_ready" in tag_set:
        return "BRK"
    if "reclaim_ready" in tag_set:
        return "RCL"
    if "near_damage_zone" in tag_set:
        return "DMG"
    if "overhead_heavy" in tag_set:
        return "OH"
    return "-"


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
    if "near_damage_zone" in from_tags:
        return "damage risk"
    return ""


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
            why = _pair_reason_tag(from_structure, to_structure) or _short_reason(
                row.get("veto_reason")
            )
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
            return (status_rank, delta_rank, blend_rank, str(r.get("symbol", "")))

        for row in sorted(rows, key=_sort_key):
            sym = str(row.get("symbol") or "")
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
                    _fmt(row.get("delta_blend")),
                    style=_delta_style(row.get("delta_blend"), thr),
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


def main() -> int:
    user_args = sys.argv[1:]

    rec_doc = read_json(REC_PATH)

    core = run_core_ui(user_args)
    prefix, detail_blocks, _detail_order = split_core_output(core)
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
    sys.stdout.write(render_overview_triscore(order_all, held_syms) + "\n")
    # 1b) Overview (A–E totals per universe) — sectors + inverses
    if inv_syms:
        pass
    #         try:
    #             inputs = rec_doc.get("inputs") if isinstance(rec_doc, dict) else None
    #             period = str(inputs.get("period")) if isinstance(inputs, dict) and inputs.get("period") else "6mo"
    #             interval = str(inputs.get("interval")) if isinstance(inputs, dict) and inputs.get("interval") else "1d"
    #
    #             rows = compute_scores(sectors=order_all, period=period, interval=interval)
    #             by = {str(r.get("symbol") or "").upper(): r for r in rows if isinstance(r, dict)}
    #
    #             def cat_sum(r, cat):
    #                 cats = r.get("categories", {})
    #                 if not isinstance(cats, dict):
    #                     return 0
    #                 node = cats.get(cat)
    #                 if not isinstance(node, dict):
    #                     return 0
    #                 checks = node.get("checks")
    #                 if not isinstance(checks, list):
    #                     return 0
    #                 s = 0
    #                 for chk in checks:
    #                     if isinstance(chk, dict) and isinstance(chk.get("score"), int):
    #                         s += int(chk["score"])
    #                 return s
    #
    #             lines2 = []
    #             lines2.append("                        Overview (A–E totals per universe)")
    #             lines2.append("")
    #             lines2.append(f"  {'Sym':<6}  {'A':>6}  {'B':>6}  {'C':>6}  {'D':>6}  {'E':>6}  {'Total':>8}")
    #             lines2.append("  " + "─" * 62)
    #             for sym in order_all:
    #                 r = by.get(sym)
    #                 if not r:
    #                     continue
    #                 a = cat_sum(r, 'A'); b = cat_sum(r, 'B'); cc = cat_sum(r, 'C'); d = cat_sum(r, 'D'); e = cat_sum(r, 'E')
    #                 total = a + b + cc + d + e
    #                 lines2.append(f"  {sym:<6}  {a:>2}/12  {b:>2}/12  {cc:>2}/12  {d:>2}/12  {e:>2}/12  {total:>2}/60")
    #             sys.stdout.write("\n".join(lines2) + "\n\n")
    #         except Exception:
    #             pass
    #
    # 1b) Overview (expanded universe, totals-only)
    if inv_syms:
        try:
            lines2 = []
            lines2.append(c("Overview (expanded universe, totals-only)", CYAN))
            lines2.append(f"{'Sym':<6}  {'Total':>12}")
            lines2.append("-" * 22)
            for sym in order_all:
                u = util.get(sym)
                if not isinstance(u, float):
                    continue
                pct = int(round(u * 100))
                letter, col = grade_letter(pct)
                lines2.append(f"{sym:<6}  {pct:>3}% {c(letter, col)}")
            sys.stdout.write("\n".join(lines2) + "\n\n")
        except Exception:
            pass

    # 2) Pi Grid
    # OVERVIEW_AE_FROM_SNAPSHOT_V2
    # Rich bordered + colorized A–E totals table from the UI snapshot (cache-only; includes inverses)
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
        from rich import box

        ui_path2 = Path(
            os.path.expanduser(
                os.environ.get(
                    "JERBOA_UI_JSON", "~/.cache/jerboa/market_health.ui.v1.json"
                )
            )
        ).expanduser()
        snap2 = read_json(ui_path2)
        data2 = snap2.get("data") if isinstance(snap2, dict) else None
        sec2 = data2.get("sectors") if isinstance(data2, dict) else None
        if isinstance(sec2, list):
            by2 = {}
            for it in sec2:
                if isinstance(it, dict):
                    sym = str(it.get("symbol") or "").strip().upper()
                    if sym:
                        by2[sym] = it

            def _cat_sum(row, cat):
                cats = row.get("categories", {})
                if not isinstance(cats, dict):
                    return 0
                node = cats.get(cat)
                if not isinstance(node, dict):
                    return 0
                checks = node.get("checks")
                if not isinstance(checks, list):
                    return 0
                total = 0
                for chk in checks:
                    if isinstance(chk, dict):
                        sc = chk.get("score")
                        try:
                            total += int(sc)
                        except Exception:
                            pass
                return total

            def _style(val, denom):
                # Traffic-light thresholds:
                # /12: <4 red, <8 yellow, else green
                # /60: <20 red, <40 yellow, else green
                if denom == 12:
                    if val >= 8:
                        return "bold green"
                    if val >= 4:
                        return "bold yellow"
                    return "bold red"
                if denom == 60:
                    if val >= 40:
                        return "bold green"
                    if val >= 20:
                        return "bold yellow"
                    return "bold red"
                return "bold"

            def _cell(val, denom):
                t = Text(f"{val}/{denom}")
                t.stylize(_style(val, denom))
                return t

            console2 = Console()
            t = Table(
                title="Overview (A–E totals per universe)",
                box=box.HEAVY_HEAD,
                header_style="bold cyan",
            )
            t.add_column("Sym", style="bold cyan", no_wrap=True)
            for k in ("A", "B", "C", "D", "E"):
                t.add_column(k, justify="right")
            t.add_column("Total", justify="right")

            for sym in order_all:
                r = by2.get(sym)
                if not r:
                    continue
                a = _cat_sum(r, "A")
                b = _cat_sum(r, "B")
                c0 = _cat_sum(r, "C")
                d = _cat_sum(r, "D")
                e = _cat_sum(r, "E")
                total = a + b + c0 + d + e
                t.add_row(
                    sym,
                    _cell(a, 12),
                    _cell(b, 12),
                    _cell(c0, 12),
                    _cell(d, 12),
                    _cell(e, 12),
                    _cell(total, 60),
                )

            console2.print(t)
            console2.print()
    except Exception:
        pass
    # --- end OVERVIEW_AE_FROM_SNAPSHOT_V2 ---
    sys.stdout.write(render_pi_grid(order_all, util) + "\n")

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

            sys.stdout.write(render_positions_triscore_ascii() + chr(10))

        except Exception as e:
            sys.stdout.write(
                c("Tri-Score ASCII unavailable: %s" % (e,) + chr(10) + chr(10), YELLOW)
            )

            for sym in held_syms:
                blk = detail_blocks.get(sym)

                if blk:
                    sys.stdout.write(blk.rstrip() + chr(10) + chr(10))

    # 4) Recommendation + READY/BLOCKED table
    sys.stdout.write(render_reco(order, util, rec_doc, held_syms))
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
