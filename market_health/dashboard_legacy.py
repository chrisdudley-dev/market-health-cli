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


def render_reco(
    order: list[str],
    util: dict[str, float],
    rec_doc: dict[str, Any],
    held_syms: list[str],
) -> str:
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

    if not isinstance(rec, dict):
        rec_path = os.path.expanduser("~/.cache/jerboa/recommendations.v1.json")

        return c(f"No recommendations cache found at {rec_path}\n", RED)

    asof = (rec.get("asof") if isinstance(rec, dict) else None) or (
        rec_doc.get("asof") if isinstance(rec_doc, dict) else None
    )

    action = rec.get("action")
    reason = rec.get("why") or rec.get("reason") or rec.get("because") or ""

    from_sym = rec.get("from_symbol")
    to_sym = rec.get("to_symbol")

    diag = rec.get("diagnostics") if isinstance(rec.get("diagnostics"), dict) else {}
    best = diag.get("best_candidate")
    weakest = diag.get("weakest_held")
    threshold = diag.get("threshold")
    delta = diag.get("delta_utility")

    weak_u = util.get(weakest) if isinstance(weakest, str) else None
    thr = float(threshold) if isinstance(threshold, (int, float)) else None

    lines: list[str] = []
    lines.append(c("=" * 28 + " Recommendation (cached) " + "=" * 28, MAGENTA))
    lines.append(f"{'asof':<14}: {asof}")
    lines.append(f"{'action':<14}: {action}")
    if action == "SWAP":
        fs = from_sym or weakest or "-"
        ts = to_sym or best or "-"
        lines.append(c(f"{'swap':<14}: {fs} -> {ts}", GREEN))
    lines.append(f"{'why':<14}: {reason}")

    if isinstance(best, str):
        lines.append(f"{'best':<14}: {best} ({fmt_u(util.get(best))})")
    if isinstance(weakest, str):
        lines.append(f"{'weakest':<14}: {weakest} ({fmt_u(weak_u)})")
    if isinstance(delta, (int, float)):
        lines.append(f"{'delta':<14}: {float(delta):.3f}")
    if thr is not None:
        lines.append(f"{'threshold':<14}: {thr:.3f}")
        if isinstance(delta, (int, float)):
            short = thr - float(delta)
            lines.append(
                f"{'shortfall':<14}: {short:.3f}"
                if short > 0
                else f"{'shortfall':<14}: 0.000"
            )

    # READY/BLOCKED table (the “denied/ready” concept)
    lines.append("")
    lines.append(c("Swap candidates vs weakest held", CYAN))
    inputs = rec_doc.get("inputs") if isinstance(rec_doc.get("inputs"), dict) else {}
    use_forecast = (
        bool(inputs.get("forecast_mode"))
        or (diag.get("decision_metric") == "robust_edge")
        or (diag.get("mode") == "forecast")
    )

    if use_forecast:
        lines.append(
            f"{'sym':<6}{'health':>10}  {'edge':>7}  {'thr':>7}  {'status':>8}"
        )
        lines.append("-" * 52)
        fs_doc = read_json(CACHE_DIR / "forecast_scores.v1.json")
        scores = fs_doc.get("scores") if isinstance(fs_doc, dict) else None
        horizons = (
            fs_doc.get("horizons_trading_days") if isinstance(fs_doc, dict) else None
        )
        if not isinstance(scores, dict) or not scores or not isinstance(weakest, str):
            lines.append(
                c("forecast scores unavailable (cannot compute robust edges)", YELLOW)
            )
        else:
            hs: list[int] = []
            if isinstance(horizons, list):
                for h in horizons:
                    try:
                        hs.append(int(h))
                    except Exception:
                        pass
            hs = sorted(set(hs)) or [1, 5]

            def iter_checks(node):
                if isinstance(node, dict):
                    if isinstance(node.get("label"), str) and "score" in node:
                        yield node
                    for v in node.values():
                        yield from iter_checks(v)
                elif isinstance(node, list):
                    for v in node:
                        yield from iter_checks(v)

            def f_util(sym: str, H: int):
                by_h = scores.get(sym)
                if not isinstance(by_h, dict):
                    return None
                payload = by_h.get(str(H), by_h.get(H))
                if payload is None:
                    return None
                chks = list(iter_checks(payload))
                if not chks:
                    return None
                s = 0.0
                for c_ in chks:
                    try:
                        s += float(c_.get("score", 0.0))
                    except Exception:
                        pass
                m_ = 2.0 * len(chks)
                return (s / m_) if m_ else None

            def robust_edge(out_sym: str, to_sym: str):
                edges = []
                for H in hs:
                    uo = f_util(out_sym, H)
                    ut = f_util(to_sym, H)
                    if uo is None or ut is None:
                        return None
                    edges.append(ut - uo)
                return min(edges) if edges else None

            held_set = set(held_syms)
            # Candidate symbols = union of overview sectors and forecast score keys, minus held and outsym
            cand_syms = sorted(set(order) | set(scores.keys()))
            cand_syms = [
                s
                for s in cand_syms
                if isinstance(s, str) and s and s not in held_set and s != weakest
            ]

            rows = []
            for sym in cand_syms:
                e = robust_edge(weakest, sym)
                if e is None:
                    continue
                rows.append((sym, util.get(sym), e))
            rows.sort(key=lambda t: (-t[2], t[0]))
            rows = rows[:6]

            for sym, hu, e in rows:
                status = "BLOCKED"
                col = YELLOW
                if thr is not None and e >= thr:
                    status = "READY"
                    col = GREEN
                elif thr is None:
                    status = "?"
                    col = YELLOW
                hu_s = f"{hu:>10.3f}" if isinstance(hu, float) else (" " * 10)
                thr_s = "" if thr is None else f"{thr:>7.3f}"
                lines.append(f"{sym:<6}{hu_s}  {e:>7.3f}  {thr_s:>7}  {c(status, col)}")

    else:
        lines.append(f"{'sym':<6}{'utility':>10}  {'Δ':>7}  {'thr':>7}  {'status':>8}")
        lines.append("-" * 44)
        held_set = set(held_syms)
        candidates = [(s, util.get(s)) for s in util.keys() if s not in held_set]
        candidates = [(s, u) for s, u in candidates if isinstance(u, float)]
        candidates.sort(key=lambda x: (-x[1], x[0]))

        for sym, u in candidates:
            d = (u - weak_u) if (weak_u is not None) else None
            status = "BLOCKED"
            col = YELLOW
            if d is not None and thr is not None and d >= thr:
                status = "READY"
                col = GREEN
            elif d is None or thr is None:
                status = "?"
                col = YELLOW
            lines.append(
                f"{sym:<6}{u:>10.3f}  {'' if d is None else f'{d:>7.3f}'}  {'' if thr is None else f'{thr:>7.3f}'}  {c(status, col)}"
            )

    lines.append(
        f"{'held_syms':<14}: {', '.join(held_syms) if held_syms else '(none found)'}"
    )
    return "\n".join(lines) + "\n"


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
