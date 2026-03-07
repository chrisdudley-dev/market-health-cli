from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# NOTE: dashboard_legacy already depends on rich; this module follows that.
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

CACHE_DIR = Path.home() / ".cache" / "jerboa"
UI_JSON = Path(os.environ.get("JERBOA_UI_JSON", str(CACHE_DIR / "market_health.ui.v1.json"))).expanduser()
FORECAST_JSON = CACHE_DIR / "forecast_scores.v1.json"
INVERSE_UNIVERSE_JSON = CACHE_DIR / "inverse_universe.v1.json"

CAT_LABELS = {
    "A": "Announcements",
    "B": "Backdrop",
    "C": "Crowding",
    "D": "Danger",
    "E": "Environment",
}

DIGIT_STYLE = {
    "0": "bold red",
    "1": "bold yellow",
    "2": "bold green",
    "-": "dim",
}


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sector_map_from_ui(ui: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sectors = ui.get("data", {}).get("sectors", [])
    out: dict[str, dict[str, Any]] = {}
    if isinstance(sectors, list):
        for it in sectors:
            if isinstance(it, dict):
                sym = str(it.get("symbol") or "").strip().upper()
                if sym:
                    out[sym] = it
    return out


def _pick_held_syms_from_ui(ui: dict[str, Any]) -> list[str]:
    held: list[str] = []
    pos = ui.get("data", {}).get("positions")
    if isinstance(pos, dict):
        rows = pos.get("positions") or []
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and isinstance(r.get("symbol"), str):
                    sym = r["symbol"].strip().upper()
                    if sym:
                        held.append(sym)
    return sorted(set(held))


def _inverse_syms_from_cache() -> list[str]:
    doc = _read_json(INVERSE_UNIVERSE_JSON)
    pairs = doc.get("pairs") if isinstance(doc, dict) else None
    if not isinstance(pairs, list):
        return []
    invs: list[str] = []
    for it in pairs:
        if isinstance(it, dict) and isinstance(it.get("inverse"), str):
            sym = it["inverse"].strip().upper()
            if sym:
                invs.append(sym)
    # de-dupe in order
    seen: set[str] = set()
    out: list[str] = []
    for s in invs:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out


def _forecast_payload_for(doc: Any, sym: str, horizon_days: int) -> dict[str, Any] | None:
    """
    forecast_scores.v1.json shape in your cache:
      doc["scores"] is dict
      doc["scores"][SYMBOL] is dict: {"1": {...}, "5": {...}}
    """
    if not isinstance(doc, dict):
        return None
    scores = doc.get("scores")
    if not isinstance(scores, dict):
        return None
    by_sym = scores.get(sym)
    if not isinstance(by_sym, dict):
        return None
    node = by_sym.get(str(horizon_days))
    return node if isinstance(node, dict) else None


def _candidate_keys(chk: dict[str, Any], idx: int) -> list[str]:
    keys: list[str] = []
    for k in ("id", "key", "name", "label", "title", "code"):
        v = chk.get(k)
        if isinstance(v, str):
            vv = v.strip().lower()
            if vv:
                keys.append(vv)
    keys.append(f"idx:{idx}")
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out


def _build_forecast_index(payload: dict[str, Any]) -> dict[tuple[str, str], int]:
    """
    Map (cat, key) -> score_int, plus (cat, idx:<n>) fallback.
    """
    out: dict[tuple[str, str], int] = {}
    cats = payload.get("categories")
    if not isinstance(cats, dict):
        return out

    for cat, node in cats.items():
        if cat not in CAT_LABELS or not isinstance(node, dict):
            continue
        checks = node.get("checks")
        if not isinstance(checks, list):
            continue
        for i, chk in enumerate(checks, start=1):
            if not isinstance(chk, dict):
                continue
            sc = chk.get("score")
            try:
                score_int = int(sc)
            except Exception:
                continue

            # store for all candidate keys + idx key
            for k in _candidate_keys(chk, i):
                out[(cat, k)] = score_int

    return out


def _digit(score: Any) -> str:
    try:
        n = int(score)
    except Exception:
        return "-"
    if n < 0:
        return "0"
    if n > 2:
        return "2"
    return str(n)


def _tri_text(c: str, h1: str, h5: str) -> Text:
    t = Text()
    t.append(c, DIGIT_STYLE.get(c, ""))
    t.append(h1, DIGIT_STYLE.get(h1, ""))
    t.append(h5, DIGIT_STYLE.get(h5, ""))
    return t


def _sum_points_from_categories(row: dict[str, Any]) -> tuple[int, int]:
    """
    Sum raw points from UI snapshot categories across A–E.
    Returns (points, max_points). Each check max is assumed 2.
    """
    cats = row.get("categories")
    if not isinstance(cats, dict):
        return (0, 0)

    pts = 0
    maxp = 0
    for cat in CAT_LABELS:
        node = cats.get(cat)
        if not isinstance(node, dict):
            continue
        checks = node.get("checks")
        if not isinstance(checks, list):
            continue
        for chk in checks:
            if not isinstance(chk, dict):
                continue
            maxp += 2
            try:
                pts += int(chk.get("score"))
            except Exception:
                pass
    return (pts, maxp)


def render_positions_triscore_ascii(h1_days: int = 1, h5_days: int = 5) -> str:
    ui = _read_json(UI_JSON)
    if not isinstance(ui, dict):
        return "Tri-Score unavailable: missing UI snapshot.\n"

    sector_map = _sector_map_from_ui(ui)
    if not sector_map:
        return "Tri-Score unavailable: UI snapshot has no sectors.\n"

    # Held + inverses (requested)
    held = _pick_held_syms_from_ui(ui)
    invs = _inverse_syms_from_cache()

    # If held is empty, default to sector ETFs from snapshot
    if not held:
        held = sorted([s for s in sector_map.keys() if s.startswith("XL")])

    # Combine: held positions only
    syms: list[str] = []
    for s in held:
        if s in sector_map and s not in syms:
            syms.append(s)

    # Forecast doc: prefer embedded forecast if present; else cache file
    fdoc = ui.get("data", {}).get("forecast_scores")
    if not isinstance(fdoc, dict):
        fdoc = _read_json(FORECAST_JSON)

    console = Console(
        record=True,
        force_terminal=True,   # keep color/borders even when stdout is redirected
        color_system="truecolor",
        width=110,
    )

    console.print(
        Panel(
            Text("My Positions — Tri-Score (C/H1/H5)", style="bold"),
            subtitle=f"cache={CACHE_DIR}",
            box=box.ROUNDED,
        )
    )

    for sym in syms:
        row = sector_map.get(sym)
        if not isinstance(row, dict):
            continue

        f1 = _forecast_payload_for(fdoc, sym, h1_days) or {}
        f5 = _forecast_payload_for(fdoc, sym, h5_days) or {}
        idx1 = _build_forecast_index(f1) if isinstance(f1, dict) else {}
        idx5 = _build_forecast_index(f5) if isinstance(f5, dict) else {}

        # Totals (%)
        c_pts, c_max = _sum_points_from_categories(row)
        c_pct = int(round((c_pts / c_max) * 100)) if c_max else 0

        h1_pts, h1_max = _sum_points_from_categories(f1) if isinstance(f1, dict) else (0, 0)
        h5_pts, h5_max = _sum_points_from_categories(f5) if isinstance(f5, dict) else (0, 0)
        h1_pct = int(round((h1_pts / h1_max) * 100)) if h1_max else None
        h5_pct = int(round((h5_pts / h5_max) * 100)) if h5_max else None

        hdr = Text()
        hdr.append(f"{sym:>6}  ", style="bold cyan")
        hdr.append("Totals (C/H1/H5): ", style="dim")
        hdr.append(f"{c_pct:>3d}%", style="bold")
        hdr.append("  ")
        hdr.append(f"{h1_pct:>3d}%" if h1_pct is not None else "  - ", style="bold" if h1_pct is not None else "dim")
        hdr.append("  ")
        hdr.append(f"{h5_pct:>3d}%" if h5_pct is not None else "  - ", style="bold" if h5_pct is not None else "dim")
        console.print(hdr)

        t = Table(box=box.SQUARE, show_header=True, header_style="bold", expand=False, pad_edge=False)
        t.add_column("Factor", justify="left", no_wrap=True)
        for i in range(1, 7):
            t.add_column(f"{i}", justify="center", no_wrap=True, width=5)
        t.add_column("Tot(C/H1/H5)", justify="right", no_wrap=True, width=13)

        cats = row.get("categories", {})
        for cat in CAT_LABELS:
            node = cats.get(cat)
            if not isinstance(node, dict):
                continue
            checks = node.get("checks")
            if not isinstance(checks, list):
                continue

            cells: list[Text] = []
            cat_c_pts = 0
            cat_h1_pts = 0
            cat_h5_pts = 0

            for i in range(1, 7):
                chk = checks[i - 1] if i - 1 < len(checks) else {}
                if not isinstance(chk, dict):
                    chk = {}

                c = _digit(chk.get("score"))
                cat_c_pts += int(c) if c != "-" else 0

                # forecast lookup: try multiple key candidates
                h1 = "-"
                h5 = "-"
                for key in _candidate_keys(chk, i):
                    if (cat, key) in idx1:
                        h1 = _digit(idx1[(cat, key)])
                        break
                for key in _candidate_keys(chk, i):
                    if (cat, key) in idx5:
                        h5 = _digit(idx5[(cat, key)])
                        break

                cat_h1_pts += int(h1) if h1 != "-" else 0
                cat_h5_pts += int(h5) if h5 != "-" else 0

                cells.append(_tri_text(c, h1, h5))

            tot = Text()
            tot.append(f"{cat_c_pts:>2d}", "bold")
            tot.append("/", "dim")
            tot.append(f"{cat_h1_pts:>2d}" if h1_pct is not None else " -", "bold" if h1_pct is not None else "dim")
            tot.append("/", "dim")
            tot.append(f"{cat_h5_pts:>2d}" if h5_pct is not None else " -", "bold" if h5_pct is not None else "dim")

            t.add_row(f"{cat} {CAT_LABELS[cat]}", *cells, tot)

        console.print(t)
        console.print()

    console.print(
        Text(
            "Note: cell digits are C/H1/H5. C comes from UI snapshot; H1/H5 come from forecast_scores.v1.json (if available).",
            style="dim",
        )
    )

    # DEDUPE_TRISCORE_OUTPUT_V5
    return ""