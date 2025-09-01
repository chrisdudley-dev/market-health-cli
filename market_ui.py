#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import random
import time
import datetime as dt

try:
    from requests.exceptions import RequestException
except ImportError:
    # fallback if requests isn't installed (e.g., in demo-only envs)
    class RequestException(Exception):  # type: ignore
        pass

from dataclasses import dataclass
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

# Pull scores + default sectors from the engine (do not re-define here)
from market_health.engine import compute_scores, SECTORS_DEFAULT

LAST_BANDS = {}  # symbol -> last committed band index (0..4) for hysteresis

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

def _row_symbol_and_score(row):
    sym = getattr(row, "symbol", getattr(row, "ticker", "?"))
    # mirror the same logic we use in the grid
    for attr in ("pct", "score", "percent", "value"):
        if hasattr(row, attr):
            val = getattr(row, attr)
            if val is not None:
                try:
                    return sym, int(round(float(val)))
                except (TypeError, ValueError):
                    pass
    return sym, 0


def _export_rows(rows, fmt: str) -> str:
    """Build a JSON or CSV string from rows."""
    import json, io, csv

    recs = []
    for r in rows:
        sym, score = _row_symbol_and_score(r)
        recs.append({"symbol": sym, "score": score})

    if fmt == "json":
        return json.dumps(recs, separators=(",", ":")) + "\n"

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["symbol", "score"])
        w.writeheader()
        w.writerows(recs)
        return buf.getvalue()

    raise ValueError("fmt must be 'json' or 'csv'")


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


# ---------- Pi Grid (compact, no legend) ----------

def render_pi_grid(
        console,
        rows,
        grid_cols: int = 0,
        mono: bool = False,
        rating_scheme: str = "hybrid",
        quantiles=(10, 30, 70, 90),
        hysteresis: int = 0,
) -> None:
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel
    from rich import box

    labels = [
        ("Strong Sell", "SS"),
        ("Sell", "S"),
        ("Hold", "H"),
        ("Buy", "B"),
        ("Strong Buy", "SB"),
    ]

    def _fixed_bounds():
        return [20, 40, 60, 80]

    def _quantile_bounds(vals, qs=(10, 30, 70, 90)):
        xs = sorted(int(v) for v in vals if v is not None)
        if not xs:
            return _fixed_bounds()

        def pct_fn(p):
            k = max(0, min(len(xs) - 1, round((p / 100) * (len(xs) - 1))))
            return xs[k]

        return [pct_fn(q) for q in qs]

    def _choose_bounds(vals, scheme="hybrid", qs=(10, 30, 70, 90), guard=5):
        f = _fixed_bounds()
        if scheme == "fixed":
            return f
        qb = _quantile_bounds(vals, qs)
        if scheme == "quantile":
            return qb
        return [max(fi - guard, min(fi + guard, qi)) for fi, qi in zip(f, qb)]

    def _band_index(score_val: int, cuts) -> int:
        c1, c2, c3, c4 = cuts
        if score_val < c1:   return 0
        if score_val < c2:   return 1
        if score_val < c3:   return 2
        if score_val < c4:   return 3
        return 4

    def _label_for_band(bi: int):
        return labels[bi]  # (long, short)

    def _panel_style(score_val: int) -> str:
        if mono:
            return ""
        if score_val >= 80: return "on green3"
        if score_val >= 60: return "on chartreuse3"
        if score_val >= 40: return "on yellow3"
        if score_val >= 20: return "on dark_orange3"
        return "on red3"

    def _get_pct(row) -> int:
        for attr in ("pct", "score", "percent", "value"):
            if hasattr(row, attr):
                val = getattr(row, attr)
                if val is not None:
                    try:
                        return int(round(float(val)))
                    except (ValueError, TypeError):
                        pass
        return 0

    # compute bounds once per render
    cross_section = [_get_pct(r) for r in rows]
    cut_points = _choose_bounds(cross_section, scheme=rating_scheme, qs=quantiles, guard=5)

    # hysteresis helpers
    def _lower_of_band(i: int) -> int:
        return 0 if i == 0 else cut_points[i - 1]

    tiles = []
    for r, pct_val in zip(rows, cross_section):
        sym = getattr(r, "symbol", getattr(r, "ticker", "?"))
        raw_band = _band_index(pct_val, cut_points)

        # apply hysteresis (if enabled)
        if hysteresis and sym in LAST_BANDS:
            last = LAST_BANDS[sym]
            commit = last
            if raw_band > last:
                # moving up: must clear lower bound of new band by >= hysteresis
                lower_needed = _lower_of_band(raw_band) + hysteresis
                if pct_val >= lower_needed:
                    commit = raw_band
            elif raw_band < last:
                # moving down: must drop under lower bound of current band by >= hysteresis
                boundary = _lower_of_band(last)
                if pct_val < boundary - hysteresis:
                    commit = raw_band
            band_idx = commit
        else:
            band_idx = raw_band

        LAST_BANDS[sym] = band_idx
        _, short_lbl = _label_for_band(band_idx)

        text = Text(justify="center", no_wrap=True)
        text.append(f"{sym}\n", style="bold")
        text.append(f"{pct_val:>3d}%\n", style="bold")
        text.append(short_lbl, style="bold")

        tiles.append(
            Panel(
                text,
                box=box.ROUNDED,
                padding=(0, 1),
                style=_panel_style(pct_val),
                border_style="black" if not mono else "white",
            )
        )

    # layout
    def _chunk(seq, n):
        for i in range(0, len(seq), n):
            yield seq[i:i + n]

    cols = grid_cols if grid_cols and grid_cols > 0 else max(1, min(10, (console.size.width - 2) // 12))
    grid = Table.grid(padding=(0, 1))
    for _ in range(cols):
        grid.add_column(no_wrap=True)

    for row_tiles in _chunk(tiles, cols):
        if len(row_tiles) < cols:
            row_tiles = row_tiles + [""] * (cols - len(row_tiles))
        grid.add_row(*row_tiles)

    console.print(grid)


# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Market Health – terminal dashboard (with Pi Grid mode)")

    # existing flags
    p.add_argument("--demo", action="store_true", help="Use generated demo data")
    p.add_argument("--json-path", type=str, default=None, help="Path to JSON dataset to render")
    p.add_argument("--sectors", nargs="*", default=None, help="Override sector tickers, e.g. --sectors XLK XLF XLY")
    p.add_argument("--period", type=str, default="1y", help="Lookback period for live fetch (yfinance), e.g. 6mo, 1y")
    p.add_argument("--interval", type=str, default="1d", help="Sampling interval, e.g. 1d, 1h")
    p.add_argument("--ttl", type=int, default=300, help="Cache TTL (seconds) for live computations")
    p.add_argument("--watch", type=int, default=0, help="Auto-refresh every N seconds (0=once)")
    p.add_argument("--topk", type=int, default=3, help="Top-K sectors to show in details (non-grid view)")
    p.add_argument("--mono", action="store_true", help="Monochrome output (disable color)")
    p.add_argument("--pi-grid", action="store_true", help="Render compact single-grid (Pi display) view")
    p.add_argument("--grid-cols", type=int, default=4, help="Columns in Pi grid (0 = auto-fit)")
    p.add_argument("--hysteresis", type=int, default=0,
                   help="Points required to cross a rating band (reduces flip-flop in --watch)")
    p.add_argument("--export", choices=["json", "csv"],
                   help="Print rows as JSON/CSV and exit")
    p.add_argument("--version", action="version", version="market-health-cli 0.2.0")

    # NEW: rating controls
    p.add_argument(
        "--rating-scheme",
        choices=["fixed", "quantile", "hybrid"],
        default="hybrid",
        help="Map 0–100 score to SB/B/H/S/SS (default: hybrid quantile/fixed)",
    )
    p.add_argument(
        "--quantiles",
        type=str,
        default="10,30,70,90",
        help="Cutpoints for quantile scheme (comma-separated), e.g. 10,30,70,90",
    )
    # (optional hysteresis — wire it later if you want)
    # p.add_argument("--hysteresis", type=int, default=0, help="Pts needed to cross a band before label changes")

    return p.parse_args()


def main():
    args = parse_args()
    console = Console(
        force_terminal=not args.mono,
        force_interactive=False,
        color_system=None if args.mono else "auto",
    )

    def load_rows() -> List[SectorRow]:
        # fall back to engine defaults if user didn't pass --sectors
        sector_list = args.sectors or SECTORS_DEFAULT

        if args.demo:
            return build_demo_dataset(sector_list, seed=42)

        if args.json_path:
            try:
                return load_json_dataset(args.json_path, args.sectors)
            except (OSError, json.JSONDecodeError) as err:
                console.print(f"[red]Failed to read JSON: {err}[/red]")
                return []

        # live from engine (catch common failure modes, not a broad Exception)
        try:
            return load_live_dataset(sector_list, args.period, args.interval, args.ttl)
        except (OSError, ValueError, RuntimeError, KeyError, RequestException) as err:
            console.print(f"[red]Failed to compute live scores: {err}[/red]")
            return []

    # ----- export mode (machine-friendly) -----
    if getattr(args, "export", None):
        rows_export = load_rows()
        text = _export_rows(rows_export, args.export)  # choices guard guarantees valid fmt
        print(text, end="")  # stdout (not Rich), no extra newline
        return

    def render_once():
        console.print()
        if args.pi_grid:
            console.rule("Market Health – Pi Grid")
            rows_local = load_rows()
            if rows_local:
                render_pi_grid(
                    console,
                    rows_local,
                    grid_cols=args.grid_cols,
                    mono=args.mono,
                    rating_scheme=args.rating_scheme,
                    quantiles=tuple(int(x) for x in args.quantiles.split(",")),
                    hysteresis=args.hysteresis,
                )
            else:
                if args.json_path:
                    console.print(f"[yellow]No matching sectors in {args.json_path}[/yellow]")
                else:
                    console.print("[yellow]No data to display.[/yellow]")
            return

        # non-Pi view
        render_header(console, mono=args.mono)
        rows_local = load_rows()
        if rows_local:
            render_overview(console, rows_local, mono=args.mono)
            render_details(console, rows_local, top_k=args.topk, mono=args.mono)
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
