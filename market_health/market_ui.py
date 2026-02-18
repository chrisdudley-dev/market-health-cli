#!/usr/bin/env python
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from rich import box
from rich.console import Console as _RichConsole
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from market_health.engine import SECTORS_DEFAULT, SECTOR_LEADERS, compute_scores
from market_health.ui_contract_meta import dimension_heading

FORCE_COLOR = bool(
    os.environ.get("MH_FORCE_COLOR")
    or os.environ.get("FORCE_COLOR")
    or os.environ.get("RICH_FORCE_TERMINAL")
)


def Console(*args, **kwargs):
    """Wrapper around Rich Console."""
    if FORCE_COLOR:
        os.environ.pop("NO_COLOR", None)
        os.environ.pop("RICH_NO_COLOR", None)

        term = os.environ.get("TERM", "")
        if (not term) or term.lower() == "dumb":
            os.environ["TERM"] = "xterm-256color"

        os.environ.setdefault("COLORTERM", "truecolor")
        kwargs["force_terminal"] = True
        kwargs["no_color"] = False
        kwargs["color_system"] = os.environ.get("MH_COLOR_SYSTEM", "auto")

    return _RichConsole(*args, **kwargs)


CHECK_LABELS: Dict[str, List[str]] = {
    "A": ["News", "Analysts", "Event", "Insiders", "Peers/Macro", "Guidance"],
    "B": ["Stacked MAs", "RS vs SPY", "BB Mid", "20D Break", "Vol x", "Hold 20EMA"],
    "C": ["EM Fit", "OI/Flow", "Blocks/DP", "Leaders%>20D", "Money Flow", "SI/Days"],
    "D": ["ATR%", "IV%", "Correlation", "Event Risk", "Gap Plan", "Sizing/RR"],
    "E": ["SPY Trend", "Sector Rank", "Breadth", "VIX Regime", "3-Day RS", "Drivers"],
    "F": ["Trigger", "Invalidation", "Targets", "Time Stop", "Slippage", "Alerts"],
}
MAX_PER_CATEGORY = 12
MAX_TOTAL = MAX_PER_CATEGORY * 6


# ---------- data structures ----------
@dataclass
class Check:
    label: str
    score: int


@dataclass
class Category:
    key: str
    checks: List[Check]

    @property
    def total(self) -> int:
        return sum(c.score for c in self.checks)


@dataclass
class SectorRow:
    symbol: str
    categories: Dict[str, Category]

    @property
    def total(self) -> int:
        return sum(cat.total for cat in self.categories.values())


# ---------- tiny render helpers ----------
def pct_style(p: float, mono: bool = False) -> str:
    if FORCE_COLOR:
        mono = False

    # Force styles even when stdout isn't a TTY (useful for piping/login banners)
    if (
        os.environ.get("MH_FORCE_COLOR")
        or os.environ.get("FORCE_COLOR")
        or os.environ.get("RICH_FORCE_TERMINAL")
    ):
        mono = False

    if mono:
        return ""
    if p >= 0.80:
        return "black on green3"
    if p >= 0.60:
        return "black on chartreuse3"
    if p >= 0.40:
        return "black on khaki1"
    if p >= 0.20:
        return "black on dark_orange3"
    return "white on red3"


def score_cell(score: int, max_score: int, mono: bool = False) -> Text:
    p = (score / max_score) if max_score else 0.0
    t = Text(f"{score}/{max_score} ({int(round(p * 100))}%)")
    style = pct_style(p, mono)
    if style:
        t.stylize(style)
    return t


def chip(s: int, mono: bool = False) -> Text:
    if mono:
        return Text("+" if s >= 2 else "~" if s == 1 else "-")
    return Text("●", style=("green3" if s >= 2 else "gold1" if s == 1 else "red3"))


# ---------- demo dataset (used only if you pass --demo) ----------
def build_demo_sector(symbol: str, rng: random.Random) -> SectorRow:
    cats: Dict[str, Category] = {}
    for key in "ABCDEF":
        checks = [Check(label, rng.choice([0, 1, 2])) for label in CHECK_LABELS[key]]
        cats[key] = Category(key, checks)
    return SectorRow(symbol, cats)


def build_demo_dataset(symbols: List[str], seed: int) -> List[SectorRow]:
    rng = random.Random(seed)
    return [build_demo_sector(s, rng) for s in symbols]


# ---------- JSON / live -> rows ----------
def build_sector_from_json(item: dict) -> SectorRow:
    cats: Dict[str, Category] = {}
    for key in "ABCDEF":
        node = item.get("categories", {}).get(key, {})
        checks_json = node.get("checks", [])
        checks: List[Check] = []
        for idx, label in enumerate(CHECK_LABELS[key]):
            score = 0
            if idx < len(checks_json):
                raw = checks_json[idx].get("score", 0)
                try:
                    score = max(0, min(2, int(raw)))
                except (ValueError, TypeError):
                    score = 0
            checks.append(Check(label, score))
        cats[key] = Category(key, checks)
    return SectorRow(symbol=item.get("symbol", "?"), categories=cats)


def load_json_dataset(
    path: str, sectors_filter: Optional[List[str]]
) -> List[SectorRow]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # ENV_V1_JSON_SUPPORT_V1: allow environment.v1.json (object) as input; use its sector list
    if isinstance(data, dict) and "sectors" in data:
        data = data["sectors"]

    rows: List[SectorRow] = []
    for item in data:
        s = build_sector_from_json(item)
        if (not sectors_filter) or (s.symbol in sectors_filter):
            rows.append(s)
    return rows


def load_live_dataset(
    sectors: List[str], period: str, interval: str, ttl: int
) -> List[SectorRow]:
    payload = compute_scores(
        sectors=sectors, period=period, interval=interval, ttl_sec=ttl
    )
    return [build_sector_from_json(obj) for obj in payload]


# ---------- rendering ----------
def render_header(console: Console, mono: bool = False) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"[bold]Market Health – Sector Union[/bold]  •  {ts}"
    if mono:
        console.print(title)
        console.print(
            "Legend: + good  ~ mixed  - weak   0–19% 20–39% 40–59% 60–79% 80–100%"
        )
        console.print()
        return
    legend = (
        "[green3]●[/green3]=good  [gold1]●[/gold1]=mixed  [red3]●[/red3]=weak   "
        "[white on red3] 0–19% [/white on red3] "
        "[black on dark_orange3] 20–39% [/black on dark_orange3] "
        "[black on khaki1] 40–59% [/black on khaki1] "
        "[black on chartreuse3] 60–79% [/black on chartreuse3] "
        "[black on green3] 80–100% [/black on green3]"
    )
    console.print(Panel.fit(legend, title=title, border_style="cyan"))


def render_overview(
    console: Console, rows: List[SectorRow], mono: bool = False
) -> None:
    tbl = Table(
        title="Overview (A–F totals per sector)", box=box.SIMPLE_HEAVY, show_lines=False
    )
    tbl.add_column("Sector", justify="left", style="bold cyan")
    for key in "ABCDEF":
        tbl.add_column(key, justify="center")
    tbl.add_column("Total", justify="center", style="bold")
    for row_data in rows:
        cells: List[Text] = [Text(row_data.symbol)]
        for key in "ABCDEF":
            cells.append(
                score_cell(row_data.categories[key].total, MAX_PER_CATEGORY, mono)
            )
        cells.append(score_cell(row_data.total, MAX_TOTAL, mono))
        tbl.add_row(*cells)
    console.print(tbl)


def render_details(
    console: Console, rows: List[SectorRow], top_k: int, mono: bool = False
) -> None:
    if not rows:
        return
    ranked = sorted(rows, key=lambda r: r.total, reverse=True)[
        : max(1, min(top_k, len(rows)))
    ]
    for row_data in ranked:
        console.rule(f"[bold magenta]Details[/bold magenta] – {row_data.symbol}")
        t = Table(box=box.MINIMAL_HEAVY_HEAD, show_lines=True)
        t.add_column("Factor", style="bold")
        for i in range(1, 7):
            t.add_column(str(i), justify="center")
        t.add_column("Cat Total", justify="center")
        for key in "ABCDEF":
            cat = row_data.categories[key]
            row_cells: List[Text] = [Text(dimension_heading(key))]
            row_cells.extend([chip(ch.score, mono) for ch in cat.checks])
            row_cells.append(score_cell(cat.total, MAX_PER_CATEGORY, mono))
            t.add_row(*row_cells)
        console.print(t)


# ---------- Pi Grid (compact, no legend) ----------
MAX_TOTAL = MAX_PER_CATEGORY * 6  # 6 categories A..F


# POSITIONS_V1_PANEL_V1: positions cache panel under the grid (read-only)


# ---------- positions -> sector mapping (best-effort) ----------
_SECTOR_OVERRIDES = None


def _load_sector_overrides() -> dict:
    """Optional overrides: ~/.config/jerboa/positions_sector_map.json
    Example: {"CSWC": "XLF"}  (maps ticker -> sector ETF)
    """
    global _SECTOR_OVERRIDES
    if _SECTOR_OVERRIDES is not None:
        return _SECTOR_OVERRIDES
    try:
        path = os.path.expanduser("~/.config/jerboa/positions_sector_map.json")
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            _SECTOR_OVERRIDES = {str(k).upper(): str(v).upper() for k, v in obj.items()}
        else:
            _SECTOR_OVERRIDES = {}
    except Exception:
        _SECTOR_OVERRIDES = {}
    return _SECTOR_OVERRIDES


def _sector_for_symbol(sym: str):
    sym = (sym or "").upper().strip()
    if not sym:
        return None
    ov = _load_sector_overrides()
    if sym in ov:
        return ov[sym]
    if sym in SECTORS_DEFAULT:
        return sym  # sector ETF itself
    for sec, leaders in SECTOR_LEADERS.items():
        if sym in set(leaders):
            return sec
    return None


def _render_positions_panel(
    console,
    mono: bool = False,
    max_rows: int = 8,
    sector_style: Optional[Dict[str, str]] = None,
) -> None:
    """Render a compact positions panel under the Pi Grid (reads ~/.cache/jerboa/positions.v1.json)."""
    try:
        import json
        from rich.panel import Panel
        from rich.table import Table
        from rich import box

        path = os.path.expanduser("~/.cache/jerboa/positions.v1.json")
        if not os.path.isfile(path):
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        positions = data.get("positions") or []
        source = data.get("source") or {}
        src_type = source.get("type") or "unknown"

        if not positions:
            msg = (
                "No positions imported yet.\n"
                "Export a Thinkorswim Position Statement CSV to:\n"
                "  ~/imports/thinkorswim\n"
                "Then run:\n"
                "  jerboa-market-health-positions-refresh"
            )
            if mono:
                console.print(
                    "Positions: none (run jerboa-market-health-positions-refresh after exporting ToS CSV)"
                )
            else:
                console.print(
                    Panel.fit(msg, title=f"Positions ({src_type})", border_style="cyan")
                )
            return

        t = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        t.add_column("Sym")
        t.add_column("Acct")
        t.add_column("Type")
        t.add_column("Qty", justify="right")
        t.add_column("Details")

        for p in positions[:max_rows]:
            sym = str(p.get("symbol", "?"))
            sym_cell = Text(sym)
            sec = _sector_for_symbol(sym)
            st = (sector_style or {}).get(sec or "", "")
            if st and ((not mono) or FORCE_COLOR):
                sym_cell.stylize(st)
            acct = str(p.get("account_label") or "")
            typ = str(p.get("asset_type", "?"))
            qty = str(p.get("qty", ""))

            details = ""
            if typ == "option":
                details = f"{p.get('expiry', '?')}  {p.get('strike', '?')}  {p.get('right', '?')}"

            t.add_row(sym_cell, acct, typ, qty, details)

        title = f"Positions ({len(positions)})  •  source={src_type}"
        if mono:
            console.print(title)
            for p in positions[:max_rows]:
                sym = str(p.get("symbol", "?"))
                typ = str(p.get("asset_type", "?"))
                qty = str(p.get("qty", ""))
                acct = str(p.get("account_label") or "")
                det = ""
                if typ == "option":
                    det = f"{p.get('expiry', '?')} {p.get('strike', '?')} {p.get('right', '?')}"
                console.print(f"- {sym}  acct={acct}  {typ}  qty={qty}  {det}".rstrip())
        else:
            console.print(Panel(t, title=title, border_style="cyan"))

    except Exception:
        # Never break the widget for positions issues
        return


def render_pi_grid(
    console: Console, rows: List[SectorRow], cols: int = 0, mono: bool = False
) -> None:
    """Compact single-grid view for Raspberry Pi / small terminals (no legend)."""
    if not rows:
        console.print("[yellow]No data to display.[/yellow]")
        return

    ranked = sorted(rows, key=lambda r: r.total, reverse=True)

    # Minimal title line; comment out if you want zero header.
    console.rule("[bold cyan]Market Health – Pi Grid[/bold cyan]")

    # --- Auto-fit column count if cols <= 0 ---
    TILE_W = 10  # uniform tile width; tweak if you want denser tiles
    GAP = 2
    if cols is None or cols <= 0:
        term_w = max(1, console.size.width)
        cols = max(1, min(len(ranked), term_w // (TILE_W + GAP)))

    # --- Build cells with uniform width and full-tile background color ---
    cells: List[Panel] = []
    for i, r in enumerate(ranked, 1):
        pct = (r.total / MAX_TOTAL) if MAX_TOTAL else 0.0
        pct_int = int(round(pct * 100))
        style = pct_style(pct, mono)  # uses your existing color thresholds

        label = Text(f"{r.symbol}\n{pct_int}%", justify="center")
        if style:
            label.stylize(style)

        cells.append(
            Panel(
                label,
                box=box.SQUARE,
                padding=(0, 1),
                border_style="cyan",
                style=style if not mono else "",
                width=TILE_W,
                title=f"#{i}",
                title_align="left",
            )
        )

    # --- Print the grid row-by-row ---
    from math import ceil

    row_count = ceil(len(cells) / cols)
    for r in range(row_count):
        chunk = cells[r * cols : (r + 1) * cols]
        if not chunk:
            continue
        row_tbl = Table.grid(padding=(0, 1))
        for _ in chunk:
            row_tbl.add_column(justify="center")
        row_tbl.add_row(*chunk)
        console.print(row_tbl)

    # ---------- CLI ----------

    # POSITIONS_V1_PANEL_V1: show read-only positions panel under the grid
    style_by_sector = {
        r.symbol: pct_style((r.total / MAX_TOTAL) if MAX_TOTAL else 0.0, mono)
        for r in rows
    }
    _render_positions_panel(console, mono=mono, sector_style=style_by_sector)


def parse_args():
    p = argparse.ArgumentParser(description="Market Health – Sector Union (Rich UI)")
    p.add_argument(
        "--sectors", nargs="+", default=SECTORS_DEFAULT, help="Tickers to include"
    )
    p.add_argument(
        "--topk", type=int, default=3, help="How many top sectors to expand in details"
    )
    p.add_argument("--mono", action="store_true", help="Monochrome (no colors)")
    p.add_argument("--watch", type=int, default=0, help="Auto-refresh every N seconds")
    # data sources
    p.add_argument(
        "--json",
        dest="json_path",
        type=str,
        help="If set, load from JSON instead of live",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="Use random demo data (ignores --json and live)",
    )
    # live compute options (used when no --json and not --demo)
    p.add_argument("--period", type=str, default="1y")
    p.add_argument("--interval", type=str, default="1d")
    p.add_argument(
        "--ttl", type=int, default=300, help="In-process cache TTL for data fetches"
    )
    p.add_argument(
        "--pi-grid",
        action="store_true",
        help="Compact Raspberry Pi grid view (one small grid)",
    )
    p.add_argument(
        "--grid-cols", type=int, default=4, help="Number of columns in the Pi grid"
    )

    return p.parse_args()


def main():
    args = parse_args()
    if (
        os.environ.get("MH_FORCE_COLOR")
        or os.environ.get("FORCE_COLOR")
        or os.environ.get("RICH_FORCE_TERMINAL")
    ):
        args.mono = False

    console = Console(
        force_terminal=not args.mono,
        force_interactive=False,
        color_system=None if args.mono else "auto",
    )

    def load_rows() -> List[SectorRow]:
        if args.demo:
            return build_demo_dataset(args.sectors, seed=42)
        if args.json_path:
            try:
                return load_json_dataset(args.json_path, args.sectors)
            except (OSError, json.JSONDecodeError) as e:
                console.print(f"[red]Failed to read JSON: {e}[/red]")
                return []
        # live from engine
        try:
            return load_live_dataset(args.sectors, args.period, args.interval, args.ttl)
        except Exception as e:
            console.print(f"[red]Failed to compute live scores: {e}[/red]")
            return []

    def render_once():
        console.print()

    rows = load_rows()
    if rows:
        use_pi_grid = getattr(args, "pi_grid", False)
        grid_cols = getattr(args, "grid_cols", 4)

        if use_pi_grid and "render_pi_grid" in globals():
            # Pi Grid prints its own legend; don't print header twice.
            render_pi_grid(console, rows, cols=grid_cols, mono=args.mono)
        else:
            render_header(console, mono=args.mono)
            render_overview(console, rows, mono=args.mono)
            render_details(console, rows, top_k=args.topk, mono=args.mono)
    else:
        if args.json_path:
            console.print(f"[yellow]No matching sectors in {args.json_path}[/yellow]")
        else:
            console.print("[yellow]No data to display.[/yellow]")

    if getattr(args, "watch", 0) and args.watch > 0:
        try:
            while True:
                console.clear()
                render_once()
                time.sleep(max(1, args.watch))
        except KeyboardInterrupt:
            return
    else:
        render_once()


if __name__ == "__main__":
    main()
