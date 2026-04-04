from __future__ import annotations
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from market_health.engine import compute_scores
from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe
from market_health.universe import get_default_scoring_symbols
from market_health.inverse_universe_v1 import load_inverse_pairs
import argparse
from datetime import datetime, timezone


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

MAX_POS_AGE_MINUTES = int(os.environ.get("JERBOA_POSITIONS_MAX_AGE_MINUTES", "15"))


def _positions_doc_is_fresh(doc: dict[str, Any]) -> bool:
    if MAX_POS_AGE_MINUTES <= 0:
        return True
    if not isinstance(doc, dict):
        return False
    ts = doc.get("__file_mtime_epoch__")
    if not isinstance(ts, (int, float)):
        return False
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return (now_ts - int(ts)) <= (MAX_POS_AGE_MINUTES * 60)


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
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                try:
                    data["__file_mtime_epoch__"] = int(p.stat().st_mtime)
                    data["__file_path__"] = str(p)
                except Exception:
                    pass
                return data
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
    output = proc.stdout if proc.stdout.strip() else proc.stderr
    return _coerce_banner_timestamp_from_cache(output)


def _coerce_banner_timestamp_from_cache(core_text: str) -> str:
    try:
        rec_doc = read_json(REC_PATH)
        snap = None
        if isinstance(rec_doc, dict):
            snap = (
                rec_doc.get("snapshot_asof")
                or rec_doc.get("asof")
                or rec_doc.get("generated_at")
            )
        if not isinstance(snap, str) or not snap:
            return core_text

        datetime.fromisoformat(snap.replace("Z", "+00:00")).astimezone(timezone.utc)
        try:
            from zoneinfo import ZoneInfo as _ZoneInfo

            _banner_tz = _ZoneInfo("America/New_York")
        except Exception:
            from datetime import timezone as _tz, timedelta as _td

            _banner_tz = _tz(_td(hours=-5), "ET")
        from datetime import datetime as _dt

        display = _dt.now(_banner_tz).strftime("%Y-%m-%d %I:%M:%S %p %Z")

        out_lines = []
        replaced = False
        for line in core_text.splitlines(True):
            plain = strip_ansi(line)
            if (
                not replaced
                and "Market Health – Sector Union" in plain
                and "•" in plain
            ):
                try:
                    from zoneinfo import ZoneInfo as _ZoneInfo

                    _banner_tz = _ZoneInfo("America/New_York")
                except Exception:
                    from datetime import timezone as _tz, timedelta as _td

                    _banner_tz = _tz(_td(hours=-5), "ET")
                from datetime import datetime as _dt

                display = _dt.now(_banner_tz).strftime("%Y-%m-%d %I:%M:%S %p %Z")
                label = f" Market Health – Sector Union • Rendered {display} "
                plain_nl = "\n" if plain.endswith("\n") else ""
                inner_width = max(10, len(plain.rstrip("\n")) - 2)
                if len(label) > inner_width:
                    label = label[:inner_width]
                new_plain = "╭" + label.center(inner_width, "─") + "╮" + plain_nl
                out_lines.append(new_plain)
                replaced = True
                continue
            out_lines.append(line)
        return "".join(out_lines)
    except Exception:
        return core_text


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


def _merged_universe_order(primary: list[str] | tuple[str, ...] | None) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    def _add(sym: object) -> None:
        if not isinstance(sym, str):
            return
        s = sym.strip().upper()
        if not s or s in seen:
            return
        seen.add(s)
        merged.append(s)

    if isinstance(primary, (list, tuple)):
        for sym in primary:
            _add(sym)

    try:
        for sym in get_default_scoring_symbols():
            _add(sym)
    except Exception:
        pass

    return merged


def extract_symbols_from_positions(doc: dict[str, Any]) -> list[str]:
    if not _positions_doc_is_fresh(doc):
        return []
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
    def _forecast_pct_from_cache(sym: str, horizon_days: int):
        import json
        from pathlib import Path

        cache_p = Path.home() / ".cache" / "jerboa" / "forecast_scores.v1.json"
        try:
            doc = json.loads(cache_p.read_text())
        except Exception:
            return None

        scores = doc.get("scores") if isinstance(doc, dict) else None
        if not isinstance(scores, dict):
            return None

        sym_doc = scores.get(sym)
        if not isinstance(sym_doc, dict):
            return None

        horizon_doc = sym_doc.get(str(horizon_days))
        if not isinstance(horizon_doc, dict):
            return None

        v = horizon_doc.get("forecast_score")
        if not isinstance(v, (int, float)):
            return None

        return float(v) * 100.0

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
        c_pct = float(util.get(sym, 0.0) * 100)
        h1_pct = _forecast_pct_from_cache(sym, 1)
        h5_pct = _forecast_pct_from_cache(sym, 5)
        blend_pct = (
            c_pct
            if h1_pct is None or h5_pct is None
            else ((0.50 * c_pct) + (0.25 * h1_pct) + (0.25 * h5_pct))
        )
        pct = int(round(blend_pct))
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


def _load_inverse_symbols_from_cache():
    try:
        inv_path = os.path.expanduser("~/.cache/jerboa/inverse_universe.v1.json")
        loaded = load_inverse_pairs(inv_path)
    except Exception:
        return []

    pairs = loaded[0] if isinstance(loaded, tuple) else loaded
    if not isinstance(pairs, list):
        return []

    out = []
    for item in pairs:
        inv = None
        if isinstance(item, dict):
            inv = item.get("inverse")
        else:
            inv = getattr(item, "inverse", None)

        if isinstance(inv, str) and inv.strip():
            out.append(inv.strip().upper())

    seen = set()
    deduped = []
    for sym in out:
        if sym not in seen:
            seen.add(sym)
            deduped.append(sym)
    return deduped


def _expanded_overview_order(base_order, held_syms):
    out = []
    seen = set()

    def _add(sym):
        if not isinstance(sym, str):
            return
        s = sym.strip().upper()
        if not s or s in seen:
            return
        seen.add(s)
        out.append(s)

    for seq in (
        base_order,
        held_syms,
        _load_inverse_symbols_from_cache(),
        get_default_scoring_symbols(),
    ):
        if isinstance(seq, (list, tuple)):
            for sym in seq:
                _add(sym)

    return out


# COMPACT_TRISCORE_OVERVIEW_V1
def render_overview_triscore(order, held_syms):
    NL = chr(10)
    cache = Path.home() / ".cache" / "jerboa"
    ui_p = cache / "market_health.ui.v1.json"
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
    table.add_column("Δ1", justify="right", no_wrap=True, width=4)
    table.add_column("Δ5", justify="right", no_wrap=True, width=4)

    fs_doc = {}
    try:
        fs_doc = json.loads(
            (Path.home() / ".cache" / "jerboa" / "forecast_scores.v1.json").read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        fs_doc = {}

    _overview_rows_unused, overview_data = _unpack_scores(
        compute_scores(
            sectors=list(dict.fromkeys(["SPY", *order])),
            period="6mo",
            interval="1d",
        )
    )

    fs_doc = _backfill_missing_forecast_scores(
        forecast_doc=fs_doc,
        symbols=[str(sym).upper() for sym in order if isinstance(sym, str)],
        data=overview_data,
        horizons=(1, 5),
    )
    forecast_scores = fs_doc.get("scores") if isinstance(fs_doc, dict) else {}

    extras_map = {}
    try:
        missing_syms = [s for s in syms if s not in sector_map]
        if missing_syms:
            extra_rows, _ = _unpack_scores(
                compute_scores(sectors=missing_syms, period="6mo", interval="1d")
            )
            for it in extra_rows:
                if isinstance(it, dict):
                    s2 = str(it.get("symbol") or "").strip().upper()
                    if s2:
                        extras_map[s2] = it
    except Exception:
        extras_map = {}

    rows = []
    for sym in syms:
        row = sector_map.get(sym) or extras_map.get(sym)
        if not isinstance(row, dict):
            continue

        c_pct = _sum_cat_pct(row)
        h1_pct = _forecast_pct(forecast_scores, sym, 1)
        h5_pct = _forecast_pct(forecast_scores, sym, 5)

        d1 = None if c_pct is None or h1_pct is None else (h1_pct - c_pct)
        d5 = None if c_pct is None or h5_pct is None else (h5_pct - c_pct)

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

        if isinstance(forecast_scores, dict):
            by_h = forecast_scores.get(sym)
            if isinstance(by_h, dict):
                h1_backfill = (by_h.get(1) or by_h.get("1") or {}).get("forecast_score")
                h5_backfill = (by_h.get(5) or by_h.get("5") or {}).get("forecast_score")

                if h1_pct is None and isinstance(h1_backfill, (int, float)):
                    h1_pct = float(h1_backfill)
                if h5_pct is None and isinstance(h5_backfill, (int, float)):
                    h5_pct = float(h5_backfill)

                if c_pct is not None and h1_pct is not None and h5_pct is not None:
                    blend_pct = (0.50 * c_pct) + (0.25 * h1_pct) + (0.25 * h5_pct)

                d1 = None if c_pct is None or h1_pct is None else (h1_pct - c_pct)
                d5 = None if c_pct is None or h5_pct is None else (h5_pct - c_pct)

                blend_txt = f"[{_pct_style(blend_pct)}]{_fmt_pct(blend_pct)}[/]"
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


def _dashboard_intraday_fresh_or_last_completed_session(value, max_age_minutes=15):
    from datetime import datetime, timezone, timedelta, time

    if not value or value == "-":
        return False

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return False
    else:
        return False

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)

    now_utc = datetime.now(timezone.utc)
    ttl = timedelta(minutes=max_age_minutes)

    try:
        import pandas_market_calendars as mcal
    except ModuleNotFoundError:
        try:
            from zoneinfo import ZoneInfo

            et_tz = ZoneInfo("America/New_York")
        except Exception:
            et_tz = timezone(timedelta(hours=-5), "ET")

        now_et = now_utc.astimezone(et_tz)
        dt_et = dt.astimezone(et_tz)

        def _last_weekday(d):
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        def _next_weekday(d):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        mins_now = now_et.hour * 60 + now_et.minute
        open_mins = 9 * 60 + 30
        close_mins = 16 * 60

        if now_et.weekday() < 5 and open_mins <= mins_now <= close_mins:
            return dt_et.date() == now_et.date() and dt >= (now_utc - ttl)

        ref_date = now_et.date()
        if now_et.weekday() < 5 and mins_now < open_mins:
            ref_date -= timedelta(days=1)
        ref_date = _last_weekday(ref_date)

        if now_et.weekday() < 5 and mins_now < open_mins:
            next_open_date = now_et.date()
        else:
            next_open_date = now_et.date() + timedelta(days=1)
        next_open_date = _next_weekday(next_open_date)

        last_close_et = datetime.combine(ref_date, time(16, 0), tzinfo=et_tz)
        next_open_et = datetime.combine(next_open_date, time(9, 30), tzinfo=et_tz)

        return dt_et.date() == ref_date or (last_close_et <= dt_et <= next_open_et)

    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(
        start_date=(now_utc - timedelta(days=10)).date().isoformat(),
        end_date=(now_utc + timedelta(days=5)).date().isoformat(),
    )
    if sched.empty:
        return False

    rows = []
    for idx, row in sched.iterrows():
        open_ts = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        close_ts = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        session_label = str(idx.date() if hasattr(idx, "date") else idx)
        rows.append((session_label, open_ts, close_ts))

    try:
        from zoneinfo import ZoneInfo

        session_tz = ZoneInfo("America/New_York")
    except Exception:
        session_tz = timezone(timedelta(hours=-5), "ET")

    dt_session = dt.astimezone(session_tz).date().isoformat()

    for session_label, open_ts, close_ts in rows:
        if open_ts <= now_utc <= close_ts:
            if dt_session != session_label:
                return False
            return dt >= (now_utc - ttl)

    prior_rows = [r for r in rows if r[2] <= now_utc]
    if not prior_rows:
        return False

    last_completed_session, _last_open, last_close = prior_rows[-1]
    future_rows = [r for r in rows if r[1] > now_utc]
    next_open = future_rows[0][1] if future_rows else (now_utc + timedelta(days=5))

    return dt_session == last_completed_session or (last_close <= dt <= next_open)


def _has_forecast_payload(
    forecast_scores: dict[str, Any] | None,
    sym: str,
    horizons: tuple[int, ...] = (1, 5),
) -> bool:
    if not isinstance(forecast_scores, dict):
        return False

    by_h = forecast_scores.get(sym.upper())
    if not isinstance(by_h, dict):
        return False

    for h in horizons:
        payload = by_h.get(h) or by_h.get(str(h))
        if not isinstance(payload, dict):
            return False
        if not isinstance(payload.get("forecast_score"), (int, float)):
            return False
    return True


def _df_to_ohlcv(df):
    if df is None or getattr(df, "empty", True):
        return None

    cols = {str(c).lower(): c for c in df.columns}
    required = {"close", "high", "low", "volume"}
    if not required.issubset(cols):
        return None

    return OHLCV(
        close=[float(x) for x in df[cols["close"]].tolist()],
        high=[float(x) for x in df[cols["high"]].tolist()],
        low=[float(x) for x in df[cols["low"]].tolist()],
        volume=[float(x) for x in df[cols["volume"]].fillna(0).tolist()],
    )


def _backfill_missing_forecast_scores(
    forecast_doc: dict[str, Any] | None,
    *,
    symbols: list[str],
    data,
    horizons: tuple[int, ...] = (1, 5),
):
    doc = dict(forecast_doc or {})
    scores = dict(doc.get("scores") or {})

    missing = [
        str(sym).upper()
        for sym in symbols
        if isinstance(sym, str)
        and sym.strip()
        and not _has_forecast_payload(scores, str(sym).upper(), horizons)
    ]
    if not missing:
        doc["scores"] = scores
        doc.setdefault("horizons_trading_days", list(horizons))
        return doc

    if not isinstance(data, dict):
        doc["scores"] = scores
        doc.setdefault("horizons_trading_days", list(horizons))
        return doc

    spy = _df_to_ohlcv(data.get("SPY"))
    if spy is None:
        doc["scores"] = scores
        doc.setdefault("horizons_trading_days", list(horizons))
        return doc

    universe = {}
    for sym in missing:
        ohlcv = _df_to_ohlcv(data.get(sym))
        if ohlcv is None:
            continue
        if len(ohlcv.close) < 30:
            continue
        universe[sym] = ohlcv

    if universe:
        extra_scores = compute_forecast_universe(
            universe=universe,
            spy=spy,
            horizons_trading_days=horizons,
            calendar={
                "schema": "calendar.v1",
                "windows": {"by_h": {str(h): {} for h in horizons}},
            },
        )
        for sym, by_h in extra_scores.items():
            scores[str(sym).upper()] = by_h

    doc["scores"] = scores
    doc.setdefault("horizons_trading_days", list(horizons))
    return doc


def render_reco(order, util, rec_doc, held_syms):
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

    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    try:
        from zoneinfo import ZoneInfo as _ZoneInfo

        _ET = _ZoneInfo("America/New_York")
    except Exception:
        _ET = _tz(_td(hours=-5), "ET")

    cached_freshness = (
        rec_doc.get("freshness") if isinstance(rec_doc.get("freshness"), dict) else {}
    )
    if not isinstance(cached_freshness, dict):
        cached_freshness = {}

    source_ts = (
        rec_doc.get("source_timestamps")
        if isinstance(rec_doc.get("source_timestamps"), dict)
        else {}
    )
    if not isinstance(source_ts, dict):
        source_ts = {}

    def _parse_iso_any(value):
        if not value or value == "-":
            return None
        if isinstance(value, _dt):
            dt = value
        elif isinstance(value, str):
            s = value.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            try:
                dt = _dt.fromisoformat(s)
            except ValueError:
                return None
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        return dt.astimezone(_tz.utc)

    def _fmt_et(value):
        dt = _parse_iso_any(value)
        if dt is None:
            return str(value or "-")
        return dt.astimezone(_ET).strftime("%Y-%m-%d %I:%M:%S %p %Z")

    def _age_seconds_now(value):
        dt = _parse_iso_any(value)
        if dt is None:
            return None
        return max(0, int((_dt.now(_tz.utc) - dt).total_seconds()))

    def _fmt_age(seconds):
        if seconds is None:
            return "-"
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m {sec:02d}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m"

    def _is_same_or_last_completed_session_now(value):
        dt = _parse_iso_any(value)
        if dt is None:
            return False
        try:
            import pandas_market_calendars as _mcal
        except Exception:
            return False

        now_utc = _dt.now(_tz.utc)
        cal = _mcal.get_calendar("NYSE")
        sched = cal.schedule(
            start_date=(now_utc - _td(days=10)).date().isoformat(),
            end_date=(now_utc + _td(days=2)).date().isoformat(),
        )
        if sched.empty:
            return False

        rows = []
        for idx, row in sched.iterrows():
            open_ts = row["market_open"].to_pydatetime().astimezone(_tz.utc)
            close_ts = row["market_close"].to_pydatetime().astimezone(_tz.utc)
            session_label = str(idx.date() if hasattr(idx, "date") else idx)
            rows.append((session_label, open_ts, close_ts))

        dt_session = dt.astimezone(_ET).date().isoformat()

        for session_label, open_ts, close_ts in rows:
            if open_ts <= now_utc <= close_ts:
                return dt_session == session_label

        prior_rows = [r for r in rows if r[2] <= now_utc]
        if not prior_rows:
            return False

        last_completed_session = prior_rows[-1][0]
        return dt_session == last_completed_session

    asof = (
        source_ts.get("snapshot_asof")
        or rec_doc.get("snapshot_asof")
        or rec_doc.get("asof")
        or computed_at
    )

    positions_asof_live = (
        source_ts.get("positions_asof")
        or rec_doc.get("positions_asof")
        or rec_doc.get("positions_source_asof")
        or rec_doc.get("positions_generated_at")
        or "-"
    )

    forecast_asof_live = (
        source_ts.get("forecast_source_asof")
        or source_ts.get("forecast_asof")
        or source_ts.get("forecast_generated_at")
        or rec_doc.get("forecast_asof")
        or rec_doc.get("forecast_generated_at")
        or "-"
    )

    sectors_asof_live = (
        source_ts.get("sectors_asof")
        or rec_doc.get("sectors_asof")
        or rec_doc.get("sectors_generated_at")
        or "-"
    )

    positions_age = _age_seconds_now(positions_asof_live)
    forecast_age = _age_seconds_now(forecast_asof_live)
    sectors_age = _age_seconds_now(sectors_asof_live)

    max_positions_age_minutes = int(
        cached_freshness.get("max_positions_age_minutes") or 15
    )

    positions_fresh = _dashboard_intraday_fresh_or_last_completed_session(
        positions_asof_live,
        max_positions_age_minutes,
    )

    forecast_fresh = _dashboard_intraday_fresh_or_last_completed_session(
        forecast_asof_live,
        max_positions_age_minutes,
    )

    sectors_fresh = _dashboard_intraday_fresh_or_last_completed_session(
        sectors_asof_live,
        15,
    )

    live_dts = [
        _parse_iso_any(positions_asof_live),
        _parse_iso_any(forecast_asof_live),
        _parse_iso_any(sectors_asof_live),
    ]
    live_dts = [dt for dt in live_dts if dt is not None]
    skew_age = (
        int((max(live_dts) - min(live_dts)).total_seconds())
        if len(live_dts) >= 2
        else None
    )

    freshness_parts = []
    if positions_fresh is not None:
        freshness_parts.append(f"p={'yes' if positions_fresh else 'no'}")
    if forecast_fresh is not None:
        freshness_parts.append(f"f={'yes' if forecast_fresh else 'no'}")
    if sectors_fresh is not None:
        freshness_parts.append(f"s={'yes' if sectors_fresh else 'no'}")
    freshness_line = ", ".join(freshness_parts) if freshness_parts else "-"

    rendered_now_display = _dt.now(_ET).strftime("%Y-%m-%d %I:%M:%S %p %Z")
    asof_display = _fmt_et(asof)
    positions_display = _fmt_et(positions_asof_live)
    forecast_display = _fmt_et(forecast_asof_live)
    computed_display = _fmt_et(computed_at)
    age_display = f"{_fmt_age(positions_age)} / {_fmt_age(forecast_age)} / {_fmt_age(sectors_age)}"
    skew_display = _fmt_age(skew_age)

    # Presentation-only truncation for the bottom candidate-pairs widget.
    # This does NOT change recommendation/scoring logic; it only limits what is shown.
    def _safe_float(v):
        try:
            return float(v)
        except Exception:
            return None

    def _safe_str(v):
        return "" if v is None else str(v)

    def _pair_sort_key(row):
        robust = _safe_float(row.get("robust_edge"))
        weighted = _safe_float(row.get("weighted_edge"))
        avg = _safe_float(row.get("avg_edge"))
        best_effort = robust
        if best_effort is None:
            best_effort = weighted
        if best_effort is None:
            best_effort = avg
        if best_effort is None:
            best_effort = -999.0
        return (
            best_effort,
            weighted if weighted is not None else -999.0,
            avg if avg is not None else -999.0,
        )

    def _interesting_pair_rows(
        rows, selected_pair_row=None, max_rows_if_action=10, max_rows_if_noop=10
    ):

        if not isinstance(rows, list):
            return [], 0

        action_is_noop = str(action).upper() == "NOOP"

        cap = max_rows_if_noop if action_is_noop else max_rows_if_action

        def _sig(row):

            return (
                _safe_str(row.get("from_symbol")),
                _safe_str(row.get("to_symbol")),
            )

        def _robust(row):

            v = _safe_float(row.get("robust_edge"))

            return v if v is not None else -999.0

        def _weighted(row):

            v = _safe_float(row.get("weighted_edge"))

            return v if v is not None else -999.0

        def _avg(row):

            v = _safe_float(row.get("avg_edge"))

            return v if v is not None else -999.0

        selected_sig = None

        if isinstance(selected_pair_row, dict):
            selected_sig = _sig(selected_pair_row)

        chosen = []

        seen = set()

        def add_row(row):

            if not isinstance(row, dict):
                return

            sig = _sig(row)

            if sig in seen:
                return

            seen.add(sig)

            chosen.append(row)

        # 1) Selected pair first.

        if selected_sig is not None:
            for row in rows:
                if _sig(row) == selected_sig:
                    add_row(row)

                    break

        # 2) Positive robust-edge rows, strongest first.

        positive_rows = [
            row
            for row in rows
            if _safe_float(row.get("robust_edge")) is not None
            and _safe_float(row.get("robust_edge")) > 0
        ]

        positive_rows.sort(
            key=lambda row: (_robust(row), _weighted(row), _avg(row)),
            reverse=True,
        )

        for row in positive_rows:
            add_row(row)

        # 3) Fill remaining slots with least-bad rows closest to zero.

        remaining_rows = [row for row in rows if _sig(row) not in seen]

        remaining_rows.sort(
            key=lambda row: (_robust(row), _weighted(row), _avg(row)),
            reverse=True,
        )

        for row in remaining_rows:
            if len(chosen) >= cap:
                break

            add_row(row)

        displayed = chosen[:cap]

        omitted = max(0, len(rows) - len(displayed))

        return displayed, omitted

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
    summary.add_row("rendered", str(rendered_now_display))
    summary.add_row("snapshot", str(asof_display))
    summary.add_row("positions", str(positions_display))
    summary.add_row("forecast", str(forecast_display))
    summary.add_row("computed", str(computed_display))
    summary.add_row("fresh", str(freshness_line))
    summary.add_row("age p/f/s", str(age_display))
    summary.add_row("skew", str(skew_display))
    summary.add_row("fp", str(fp))
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

        displayed_pair_rows, omitted_pair_rows = _interesting_pair_rows(
            pair_rows,
            selected_pair_row=selected_pair,
            max_rows_if_action=10,
            max_rows_if_noop=10,
        )

        for row in displayed_pair_rows:
            frm = str(row.get("from_symbol") or "")
            to = str(row.get("to_symbol") or "")
            frm_comp = _blend_components(frm) or {}
            to_comp = _blend_components(to) or {}
            vetoed = bool(row.get("vetoed"))
            why = _short_reason(row.get("veto_reason"))
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

        if omitted_pair_rows > 0:
            ptbl.add_row(
                "...",
                "...",
                "...",
                "...",
                "...",
                "...",
                "...",
                "...",
                "...",
                f"{omitted_pair_rows} more pairs omitted",
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
            return (status_rank, delta_rank, blend_rank, str(r.get("sym", "")))

        for row in sorted(rows, key=_sort_key):
            sym = str(row.get("sym") or "")
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


def main() -> int:
    user_args = sys.argv[1:]

    rec_doc = read_json(REC_PATH)

    core = run_core_ui(user_args)
    prefix, detail_blocks, _detail_order = split_core_output(core)
    order, util = parse_overview_totals(prefix)
    order_all = _merged_universe_order(order)

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
            snap_order, util = _snapshot_order_util(snap)
            order_all = _merged_universe_order(snap_order)

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
                        if sym in detail_blocks:
                            held_syms.append(sym)
                held_syms = sorted(set(held_syms))
        except Exception:
            pass

    # 1) Overview
    sys.stdout.write(strip_core_overview(prefix).rstrip() + "\n\n")
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
    #             for sym in overview_order:
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
    # 1b) Overview (expanded universe, totals-only) removed
    overview_order = _expanded_overview_order(order_all, held_syms)
    # 2) Pi Grid
    # OVERVIEW_AE_FROM_COMPUTE_SCORES_V2
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
        from rich import box

        inputs = rec_doc.get("inputs") if isinstance(rec_doc, dict) else None
        period = (
            str(inputs.get("period"))
            if isinstance(inputs, dict) and inputs.get("period")
            else "6mo"
        )
        interval = (
            str(inputs.get("interval"))
            if isinstance(inputs, dict) and inputs.get("interval")
            else "1d"
        )

        rows2 = compute_scores(sectors=overview_order, period=period, interval=interval)

        data2 = None

        if isinstance(rows2, tuple) and len(rows2) == 2:
            rows2, data2 = rows2

        forecast_doc = _backfill_missing_forecast_scores(
            forecast_doc={},
            symbols=overview_order,
            data=data2,
            horizons=(1, 5),
        )
        forecast_scores = (
            forecast_doc.get("scores") if isinstance(forecast_doc, dict) else {}
        )
        if isinstance(rows2, tuple) and len(rows2) == 2:
            rows2 = rows2[0]

        by2 = {}
        if isinstance(rows2, list):
            for it in rows2:
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

        if isinstance(forecast_scores, dict):
            for sym, row in by2.items():
                if not isinstance(row, dict):
                    continue

                by_h = forecast_scores.get(sym)
                if not isinstance(by_h, dict):
                    continue

                h1_payload = by_h.get(1) or by_h.get("1") or {}
                h5_payload = by_h.get(5) or by_h.get("5") or {}

                h1_score = h1_payload.get("forecast_score")
                h5_score = h5_payload.get("forecast_score")

                current_utility = _cat_sum(row, "A") + _cat_sum(row, "B")
                current_utility += _cat_sum(row, "C") + _cat_sum(row, "D")
                current_utility += _cat_sum(row, "E")
                current_utility = float(current_utility) / 60.0

                row["current_utility"] = current_utility
                row["c"] = current_utility

                if isinstance(h1_score, (int, float)):
                    row["h1_utility"] = float(h1_score)
                    row["h1"] = float(h1_score)

                if isinstance(h5_score, (int, float)):
                    row["h5_utility"] = float(h5_score)
                    row["h5"] = float(h5_score)

                if isinstance(h1_score, (int, float)) and isinstance(
                    h5_score, (int, float)
                ):
                    blended = (
                        (current_utility * 0.5)
                        + (float(h1_score) * 0.25)
                        + (float(h5_score) * 0.25)
                    )
                    row["utility"] = blended
                    row["blended"] = blended
                    row["delta_h1"] = float(h1_score) - current_utility
                    row["delta_h5"] = float(h5_score) - current_utility
                    row["d1"] = float(h1_score) - current_utility
                    row["d5"] = float(h5_score) - current_utility

        def _style(val, denom):
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

        for sym in overview_order:
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
    tri_overview = render_overview_triscore(overview_order, held_syms)
    if tri_overview:
        sys.stdout.write(tri_overview + chr(10))

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
