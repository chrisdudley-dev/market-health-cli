#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import random
import time
import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

# Pull scores + default sectors from the engine (do not re-define here)
from market_health.engine import compute_scores, SECTORS_DEFAULT

CATEGORY_NAMES: Dict[str, str] = {
    "A": "Catalyst Health", "B": "Trend & Structure", "C": "Position & Flow",
    "D": "Risk & Volatility", "E": "Environment & Regime", "F": "Execution & Frictions",
}
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
    if mono: return ""
    if p >= 0.80: return "black on green3"
    if p >= 0.60: return "black on chartreuse3"
    if p >= 0.40: return "black on khaki1"
    if p >= 0.20: return "black on dark_orange3"
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

def load_json_dataset(path: str, sectors_filter: Optional[List[str]]) -> List[SectorRow]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows: List[SectorRow] = []
    for item in data:
        s = build_sector_from_json(item)
        if (not sectors_filter) or (s.symbol in sectors_filter):
            rows.append(s)
    return rows

def load_live_dataset(sectors: List[str], period: str, interval: str, ttl: int) -> List[SectorRow]:
    payload = compute_scores(sectors=sectors, period=period, interval=interval, ttl_sec=ttl)
    return [build_sector_from_json(obj) for obj in payload]

# ---------- rendering ----------
def render_header(console: Console, mono: bool = False) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"[bold]Market Health – Sector Union[/bold]  •  {ts}"
    if mono:
        console.print(title)
        console.print("Legend: + good  ~ mixed  - weak   0–19% 20–39% 40–59% 60–79% 80–100%")
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

def render_overview(console: Console, rows: List[SectorRow], mono: bool = False) -> None:
    tbl = Table(title="Overview (A–F totals per sector)", box=box.SIMPLE_HEAVY, show_lines=False)
    tbl.add_column("Sector", justify="left", style="bold cyan")
    for key in "ABCDEF":
        tbl.add_column(key, justify="center")
    tbl.add_column("Total", justify="center", style="bold")
    for row_data in rows:
        cells: List[Text] = [Text(row_data.symbol)]
        for key in "ABCDEF":
            cells.append(score_cell(row_data.categories[key].total, MAX_PER_CATEGORY, mono))
        cells.append(score_cell(row_data.total, MAX_TOTAL, mono))
        tbl.add_row(*cells)
    console.print(tbl)

def render_details(console: Console, rows: List[SectorRow], top_k: int, mono: bool = False) -> None:
    if not rows:
        return
    ranked = sorted(rows, key=lambda r: r.total, reverse=True)[:max(1, min(top_k, len(rows)))]
    for row_data in ranked:
        console.rule(f"[bold magenta]Details[/bold magenta] – {row_data.symbol}")
        t = Table(box=box.MINIMAL_HEAVY_HEAD, show_lines=True)
        t.add_column("Factor", style="bold")
        for i in range(1, 7):
            t.add_column(str(i), justify="center")
        t.add_column("Cat Total", justify="center")
        for key in "ABCDEF":
            cat = row_data.categories[key]
            row_cells: List[Text] = [Text(f"{key}  {CATEGORY_NAMES[key]}")]
            row_cells.extend([chip(ch.score, mono) for ch in cat.checks])
            row_cells.append(score_cell(cat.total, MAX_PER_CATEGORY, mono))
            t.add_row(*row_cells)
        console.print(t)

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Market Health – Sector Union (Rich UI)")
    p.add_argument("--sectors", nargs="+", default=SECTORS_DEFAULT, help="Tickers to include")
    p.add_argument("--topk", type=int, default=3, help="How many top sectors to expand in details")
    p.add_argument("--mono", action="store_true", help="Monochrome (no colors)")
    p.add_argument("--watch", type=int, default=0, help="Auto-refresh every N seconds")
    # data sources
    p.add_argument("--json", dest="json_path", type=str, help="If set, load from JSON instead of live")
    p.add_argument("--demo", action="store_true", help="Use random demo data (ignores --json and live)")
    # live compute options (used when no --json and not --demo)
    p.add_argument("--period", type=str, default="1y")
    p.add_argument("--interval", type=str, default="1d")
    p.add_argument("--ttl", type=int, default=300, help="In-process cache TTL for data fetches")
    return p.parse_args()

def main():
    args = parse_args()
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
        render_header(console, mono=args.mono)
        rows = load_rows()
        if rows:
            render_overview(console, rows, mono=args.mono)
            render_details(console, rows, top_k=args.topk, mono=args.mono)
        else:
            if args.json_path:
                console.print(f"[yellow]No matching sectors in {args.json_path}[/yellow]")
            else:
                console.print("[yellow]No data to display.[/yellow]")

    if args.watch and args.watch > 0:
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
