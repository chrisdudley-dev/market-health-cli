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
    # Preserve held symbols for display even when the positions cache is stale.
    out: list[str] = []
    seen: set[str] = set()

    if not isinstance(doc, dict):
        return out

    rows = doc.get("positions")
    if not isinstance(rows, list):
        return out

    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def pick_positions(detail_blocks: dict[str, str], rec_doc: dict[str, Any]) -> list[str]:
    # Always prefer the normalized positions cache for held symbols.
    # Do not pre-filter by detail_blocks or sector membership here.
    pos_paths = [
        CACHE_DIR / "positions.v1.json",
        CACHE_DIR / "positions.v0.json",
        CACHE_DIR / "positions.json",
        CACHE_DIR / "market_health.positions.json",
    ]

    for path in pos_paths:
        try:
            doc = read_json(path)
        except Exception:
            continue
        syms = extract_symbols_from_positions(doc)
        if syms:
            out: list[str] = []
            seen: set[str] = set()
            for sym in syms:
                ss = str(sym or "").strip().upper()
                if ss and ss not in seen:
                    seen.add(ss)
                    out.append(ss)
            return out

    # fallback: held_scored from recommendations cache
    diag = rec_doc.get("diagnostic") if isinstance(rec_doc, dict) else None
    held = diag.get("held_scored") if isinstance(diag, dict) else None
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(held, list):
        for sym in held:
            ss = str(sym or "").strip().upper()
            if ss and ss not in seen:
                seen.add(ss)
                out.append(ss)
    return out


def grade_letter(pct: int) -> tuple[str, str]:
    if pct >= 60:
        return "B", GREEN
    if pct >= 45:
        return "H", YELLOW
    return "S", RED


def _coherent_reco_summary_from_obj(obj):
    if not isinstance(obj, dict):
        return None

    def _num(v):
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except Exception:
                return None
        return None

    def _sym_from_dict(d):
        if not isinstance(d, dict):
            return None
        lower = {str(k).lower(): v for k, v in d.items()}
        for key in (
            "sym",
            "symbol",
            "ticker",
            "candidate",
            "to",
            "to_sym",
            "to_symbol",
        ):
            v = lower.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip().upper()
        return None

    def _get(d, *names):
        lower = {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}
        for name in names:
            val = _num(lower.get(name.lower()))
            if val is not None:
                return val
        return None

    found = []

    def _walk(x):
        if isinstance(x, dict):
            sym = _sym_from_dict(x)
            if sym:
                c = _get(x, "c", "current", "score_c", "current_score")
                h1 = _get(x, "h1", "score_h1", "forecast_h1")
                h5 = _get(x, "h5", "score_h5", "forecast_h5")
                blend = _get(x, "blend", "score", "utility", "blended", "blend_score")
                if (
                    c is not None
                    or h1 is not None
                    or h5 is not None
                    or blend is not None
                ):
                    if c is not None and h1 is not None and h5 is not None:
                        blend = round((0.50 * c) + (0.25 * h1) + (0.25 * h5), 2)
                    found.append((sym, blend, c, h1, h5))
            for v in x.values():
                _walk(v)
        elif isinstance(x, list):
            for v in x:
                _walk(v)

    _walk(obj)

    scored = [t for t in found if t[1] is not None]
    if not scored:
        return None

    best = max(scored, key=lambda t: (t[1], t[0]))
    weakest = min(scored, key=lambda t: (t[1], t[0]))
    delta = round(best[1] - weakest[1], 2)

    def _fmt(v):
        return "-" if v is None else f"{v:.2f}"

    return {
        "best": f"{best[0]}  (blend {_fmt(best[1])} | C {_fmt(best[2])} | H1 {_fmt(best[3])} | H5 {_fmt(best[4])})",
        "weakest": f"{weakest[0]}  (blend {_fmt(weakest[1])} | C {_fmt(weakest[2])} | H1 {_fmt(weakest[3])} | H5 {_fmt(weakest[4])})",
        "delta": delta,
    }


def _forecast_score_to_current_utility(forecast_score, current_utility):
    try:
        fs = float(forecast_score)
    except Exception:
        return None
    if abs(fs) > 1.000001:
        fs = fs / 100.0
    fs = max(0.0, min(1.0, fs))

    try:
        cur = float(current_utility)
    except Exception:
        return fs
    if abs(cur) > 1.000001:
        cur = cur / 100.0
    cur = max(0.0, min(1.0, cur))

    anchored = cur + (fs - 0.50)
    return max(0.0, min(1.0, anchored))


def _blend_from_components(c_val, h1_val, h5_val):
    pieces = []
    for w, v in ((0.50, c_val), (0.25, h1_val), (0.25, h5_val)):
        if not isinstance(v, (int, float)):
            continue
        x = float(v)
        if abs(x) > 1.000001:
            x = x / 100.0
        x = max(0.0, min(1.0, x))
        pieces.append((w, x))
    if not pieces:
        return None
    return sum(w * x for w, x in pieces) / sum(w for w, _ in pieces)


def _extract_blend_from_comp_line(text):
    try:
        m = re.search(r"blend\s+([0-9]+(?:\.[0-9]+)?)", str(text))
        return float(m.group(1)) if m else None
    except Exception:
        return None


def _coherent_reco_summary_from_rows(rows):
    if not isinstance(rows, list):
        return None
    return _coherent_reco_summary_from_obj({"rows": rows})


def _coherent_reco_policy_from_obj(obj):
    if not isinstance(obj, dict):
        return None

    def _num(v):
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except Exception:
                return None
        return None

    def _lower_map(d):
        return {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}

    def _sym(d):
        lower = _lower_map(d)
        for key in (
            "sym",
            "symbol",
            "ticker",
            "candidate",
            "to",
            "to_sym",
            "to_symbol",
        ):
            v = lower.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip().upper()
        return None

    def _get(d, *names):
        lower = _lower_map(d)
        for name in names:
            val = _num(lower.get(name.lower()))
            if val is not None:
                return val
        return None

    found = []

    def _walk(x):
        if isinstance(x, dict):
            sym = _sym(x)
            if sym:
                c = _get(x, "c", "current", "score_c", "current_score")
                h1 = _get(x, "h1", "score_h1", "forecast_h1")
                h5 = _get(x, "h5", "score_h5", "forecast_h5")
                blend = _get(x, "blend", "score", "utility", "blended", "blend_score")
                if c is not None and h1 is not None and h5 is not None:
                    blend = round((0.50 * c) + (0.25 * h1) + (0.25 * h5), 2)
                status = None
                lower = _lower_map(x)
                for key in ("status", "state", "why", "reason", "veto_reason"):
                    v = lower.get(key)
                    if isinstance(v, str) and v.strip():
                        status = v.strip()
                        break
                found.append(
                    {
                        "sym": sym,
                        "blend": blend,
                        "status": status,
                    }
                )
            for v in x.values():
                _walk(v)
        elif isinstance(x, list):
            for v in x:
                _walk(v)

    _walk(obj)

    for r in found:
        if isinstance(r, dict):
            pieces = []
            for w, key in ((0.50, "c"), (0.25, "h1"), (0.25, "h5")):
                v = r.get(key)
                if not isinstance(v, (int, float)):
                    continue
                x = float(v)
                if abs(x) > 1.000001:
                    x = x / 100.0
                x = max(0.0, min(1.0, x))
                pieces.append((w, x))
            if pieces:
                b = sum(w * x for w, x in pieces) / sum(w for w, _ in pieces)
                r["blend"] = b
                r["blended"] = b
                r["utility"] = b
    scored = [r for r in found if r.get("blend") is not None]
    if not scored:
        return None

    best = max(scored, key=lambda r: (r["blend"], r["sym"]))
    statuses = [
        str(r.get("status") or "").upper()
        for r in scored
        if str(r.get("status") or "").strip()
    ]

    all_blocked = bool(statuses) and all("BLOCK" in s for s in statuses)
    any_unblocked = any("BLOCK" not in s for s in statuses) if statuses else False

    return {
        "best_blend": best.get("blend"),
        "all_blocked": all_blocked,
        "any_unblocked": any_unblocked,
        "status_count": len(statuses),
    }


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


def _direct_structure_summary_from_df(df):
    import math

    try:
        import pandas as pd
    except Exception:
        return {}

    if df is None or getattr(df, "empty", True):
        return {}

    cols = {str(c).lower(): c for c in getattr(df, "columns", [])}
    if not {"close", "high", "low"}.issubset(cols):
        return {}

    try:
        close = df[cols["close"]].astype(float)
        high = df[cols["high"]].astype(float)
        low = df[cols["low"]].astype(float)
    except Exception:
        return {}

    if len(close) < 20:
        return {}

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(14, min_periods=5).mean()
    if atr.empty:
        return {}

    atr_last = float(atr.iloc[-1])
    last_close = float(close.iloc[-1])
    if not math.isfinite(atr_last) or atr_last <= 0 or not math.isfinite(last_close):
        return {}

    recent_low = float(low.tail(20).min())
    recent_high = float(high.tail(20).max())

    support_cushion_atr = max(0.0, (last_close - recent_low) / atr_last)
    overhead_resistance_atr = max(0.0, (recent_high - last_close) / atr_last)

    stop = recent_low - (0.25 * atr_last)
    buy = recent_high + (0.25 * atr_last)

    state_tags = []
    if support_cushion_atr <= 0.25:
        state_tags.append("near_damage_zone")
    elif support_cushion_atr <= 0.75:
        state_tags.append("reclaim_ready")

    if overhead_resistance_atr <= 0.25:
        state_tags.append("breakout_ready")
    elif overhead_resistance_atr <= 1.00:
        state_tags.append("overhead_heavy")

    return {
        "support_cushion_atr": round(support_cushion_atr, 6),
        "support_atr": round(support_cushion_atr, 6),
        "sup_atr": round(support_cushion_atr, 6),
        "overhead_resistance_atr": round(overhead_resistance_atr, 6),
        "resistance_atr": round(overhead_resistance_atr, 6),
        "res_atr": round(overhead_resistance_atr, 6),
        "state_tags": state_tags,
        "state_text": ",".join(state_tags) if state_tags else "-",
        "stop": round(stop, 6),
        "stop_candidate": round(stop, 6),
        "catastrophic_stop_candidate": round(stop, 6),
        "buy": round(buy, 6),
        "buy_candidate": round(buy, 6),
        "stop_buy_candidate": round(buy, 6),
        "breakout_trigger": round(buy, 6),
    }


def _structure_summary_for_symbol(fs_doc, symbol, *, horizon=None, frames_map=None):
    if not isinstance(fs_doc, dict):
        fs_doc = {}

    scores = fs_doc.get("scores") or {}
    if not isinstance(scores, dict):
        scores = {}

    sym = str(symbol or "").upper().strip()
    if not sym:
        return {}

    by_h = scores.get(sym) or {}
    if not isinstance(by_h, dict):
        by_h = {}

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

    if isinstance(payload, dict):
        ss = payload.get("structure_summary")
        if not isinstance(ss, dict):
            ss = {}

        sup = (
            ss.get("support_cushion_atr")
            or _walk_find(
                ss, ["support_cushion_atr", "support_atr", "sup_atr", "supatr"]
            )
            or _walk_find(
                payload, ["support_cushion_atr", "support_atr", "sup_atr", "supatr"]
            )
        )
        res = (
            ss.get("overhead_resistance_atr")
            or _walk_find(
                ss, ["overhead_resistance_atr", "resistance_atr", "res_atr", "resatr"]
            )
            or _walk_find(
                payload,
                ["overhead_resistance_atr", "resistance_atr", "res_atr", "resatr"],
            )
        )
        state_tags = ss.get("state_tags")
        if not isinstance(state_tags, list):
            state_tags = _walk_find(payload, ["state_tags"])
        if not isinstance(state_tags, list):
            state_tags = []
        state_text = (
            ss.get("state_text")
            or _walk_find(ss, ["state_text", "structure_state", "state"])
            or _walk_find(
                payload,
                [
                    "state_text",
                    "structure_state",
                ],
            )
        )
        stop = (
            ss.get("tactical_stop_candidate")
            or ss.get("catastrophic_stop_candidate")
            or _walk_find(
                ss,
                [
                    "stop",
                    "stop_candidate",
                    "catastrophic_stop_candidate",
                    "tactical_stop_candidate",
                ],
            )
            or _walk_find(
                payload,
                [
                    "stop",
                    "stop_candidate",
                    "catastrophic_stop_candidate",
                    "tactical_stop_candidate",
                ],
            )
        )
        buy = (
            ss.get("stop_buy_candidate")
            or ss.get("breakout_trigger")
            or _walk_find(
                ss, ["buy", "buy_candidate", "stop_buy_candidate", "breakout_trigger"]
            )
            or _walk_find(
                payload,
                ["buy", "buy_candidate", "stop_buy_candidate", "breakout_trigger"],
            )
        )

        if any(
            v not in (None, "", [], {})
            for v in (sup, res, state_tags, state_text, stop, buy)
        ):
            out = dict(ss) if isinstance(ss, dict) else {}
            out.setdefault("support_cushion_atr", sup)
            out.setdefault("support_atr", sup)
            out.setdefault("sup_atr", sup)
            out.setdefault("overhead_resistance_atr", res)
            out.setdefault("resistance_atr", res)
            out.setdefault("res_atr", res)
            out.setdefault("state_tags", state_tags)
            out.setdefault(
                "state_text",
                ",".join(str(x) for x in state_tags if x)
                if state_tags
                else (state_text or "-"),
            )
            out.setdefault("stop", stop)
            out.setdefault("stop_candidate", stop)
            out.setdefault("catastrophic_stop_candidate", stop)
            out.setdefault("buy", buy)
            out.setdefault("buy_candidate", buy)
            out.setdefault("stop_buy_candidate", buy)
            out.setdefault("breakout_trigger", buy)
            out.setdefault("payload", payload)
            return out

    if isinstance(frames_map, dict):
        direct = _direct_structure_summary_from_df(frames_map.get(sym))
        if direct:
            return direct

    return {}


def _ensure_forecast_payloads(
    forecast_doc,
    symbols,
    *,
    period="6mo",
    interval="1d",
    horizons=(1, 5),
):
    if not isinstance(forecast_doc, dict):
        forecast_doc = {}

    scores = forecast_doc.get("scores")
    if not isinstance(scores, dict):
        scores = {}
        forecast_doc["scores"] = scores

    syms = []
    for sym in symbols or []:
        s = str(sym or "").upper().strip()
        if s and s not in syms:
            syms.append(s)

    def _has_forecast_horizons(sym):
        by_h = scores.get(sym)
        if not isinstance(by_h, dict):
            return False
        for h in horizons:
            payload = by_h.get(str(h), by_h.get(h))
            if not isinstance(payload, dict):
                return False
            if not isinstance(payload.get("forecast_score"), (int, float)):
                return False
        return True

    missing = [sym for sym in syms if not _has_forecast_horizons(sym)]
    if not missing:
        if not isinstance(forecast_doc.get("horizons_trading_days"), list):
            forecast_doc["horizons_trading_days"] = [int(h) for h in horizons]
        return forecast_doc

    try:
        from market_health.forecast_score_provider import compute_forecast_universe
    except Exception:
        return forecast_doc

    frames = _download_price_frames(["SPY", *missing], period=period, interval=interval)
    if not isinstance(frames, dict):
        return forecast_doc

    spy_ohlcv = _df_to_ohlcv(frames.get("SPY"))
    if spy_ohlcv is None:
        return forecast_doc

    universe = {}
    for sym in missing:
        ohlcv = _df_to_ohlcv(frames.get(sym))
        if ohlcv is not None:
            universe[sym] = ohlcv

    if not universe:
        return forecast_doc

    try:
        new_scores = compute_forecast_universe(
            universe=universe,
            spy=spy_ohlcv,
            horizons_trading_days=tuple(int(h) for h in horizons),
            calendar={
                "schema": "calendar.v1",
                "windows": {"by_h": {str(int(h)): {} for h in horizons}},
            },
        )
    except Exception:
        return forecast_doc

    if isinstance(new_scores, dict):
        for sym, payload in new_scores.items():
            if isinstance(sym, str) and isinstance(payload, dict):
                scores[str(sym).upper()] = payload

    if not isinstance(forecast_doc.get("horizons_trading_days"), list):
        forecast_doc["horizons_trading_days"] = [int(h) for h in horizons]

    return forecast_doc


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


def render_overview_triscore(order, util, held_syms):
    import io
    import json
    from pathlib import Path

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
            return float(s) if s else None
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
        return "-" if n is None else f"{n:.2f}"

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

    def _rowmaps_from_any(doc, allowed):
        out = {}

        def ingest(obj):
            if isinstance(obj, list):
                for item in obj:
                    ingest(item)
                return
            if not isinstance(obj, dict):
                return

            sym = _norm(obj.get("symbol") or obj.get("sym") or obj.get("ticker"))
            if sym and (not allowed or sym in allowed):
                out.setdefault(sym, {}).update(obj)

            for k in ("rows", "items", "data", "sectors", "state", "scores"):
                v = obj.get(k)
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

    def _row_total_pct(row):
        cats = row.get("categories") if isinstance(row, dict) else None
        if not isinstance(cats, dict):
            return None
        pts = 0.0
        mx = 0.0
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
                    pts += float(sc)
                    mx += 2.0
        return (pts / mx) if mx else None

    ui = _jload(ui_p)
    fs = _jload(fs_p)
    sectors = _jload(sectors_p)
    inv = _jload(inv_p)

    live_rows = []
    live_data = None
    try:
        live_syms = [_norm(s) for s in (order or []) if _norm(s)]
        live_universe = list(dict.fromkeys(["SPY", *live_syms]))
        live_rows, live_data = _unpack_scores(
            compute_scores(sectors=live_universe, period="6mo", interval="1d")
        )
    except Exception:
        live_rows, live_data = [], None

    fs = _backfill_missing_forecast_scores(
        forecast_doc=fs if isinstance(fs, dict) else {},
        symbols=[_norm(s) for s in (order or []) if _norm(s)],
        data=live_data,
        horizons=(1, 5),
    )
    fs = _ensure_forecast_payloads(
        fs,
        [_norm(s) for s in (order or []) if _norm(s)],
        period="6mo",
        interval="1d",
        horizons=(1, 5),
    )

    util_map = util if isinstance(util, dict) else {}
    held_set = {_norm(x) for x in (held_syms or []) if _norm(x)}
    allowed = set()
    allowed.update(_norm(s) for s in (order or []) if _norm(s))
    allowed.update(held_set)
    allowed.update(_norm(s) for s in util_map.keys() if _norm(s))
    scores_obj = fs.get("scores") if isinstance(fs, dict) else {}
    if isinstance(scores_obj, dict):
        allowed.update(_norm(s) for s in scores_obj.keys() if _norm(s))

    inv_to_long = {}
    pairs = inv.get("pairs") if isinstance(inv, dict) else None
    if isinstance(pairs, list):
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            long_sym = _norm(pair.get("long"))
            inv_sym = _norm(pair.get("inverse"))
            if long_sym and inv_sym:
                inv_to_long[inv_sym] = long_sym

    for src, dst in _proxy_overrides().items():
        if _norm(src) and _norm(dst):
            inv_to_long[_norm(src)] = _norm(dst)
            allowed.add(_norm(src))
            allowed.add(_norm(dst))

    data = ui.get("data") if isinstance(ui, dict) else {}
    rows = {}
    for src in (
        _rowmaps_from_any(sectors, allowed),
        _rowmaps_from_any(
            data.get("sectors") if isinstance(data, dict) else {}, allowed
        ),
        _rowmaps_from_any(data.get("state") if isinstance(data, dict) else {}, allowed),
    ):
        for sym, row in src.items():
            rows.setdefault(sym, {}).update(row)

    for row in live_rows or []:
        if not isinstance(row, dict):
            continue
        sym = _norm(row.get("symbol") or row.get("sym") or row.get("ticker"))
        if sym and sym in allowed:
            rows.setdefault(sym, {}).update(row)

    universe = sorted(s for s in allowed if s and s != "XLV")
    structure_frames = _download_price_frames(universe, period="6mo", interval="1d")
    H1, H5 = _forecast_horizons(fs)

    display_rows = []
    for sym in universe:
        proxy_sym = _proxy_for_symbol(sym, inv_to_long)
        row = rows.get(sym, {})
        proxy_row = rows.get(proxy_sym, {})

        c_val = _first_pct(
            util_map.get(sym),
            util_map.get(proxy_sym),
            _row_total_pct(row),
            _row_total_pct(proxy_row),
            row.get("c"),
            proxy_row.get("c"),
            _walk_find(row, ["c", "crowding", "crowding_util", "c_util"]),
            _walk_find(proxy_row, ["c", "crowding", "crowding_util", "c_util"]),
        )
        h1_val = _first_pct(
            _forecast_util(fs, sym, H1),
            _forecast_util(fs, proxy_sym, H1),
        )
        h5_val = _first_pct(
            _forecast_util(fs, sym, H5),
            _forecast_util(fs, proxy_sym, H5),
        )

        pieces = []
        if c_val is not None:
            pieces.append((0.50, c_val))
        if h1_val is not None:
            pieces.append((0.25, h1_val))
        if h5_val is not None:
            pieces.append((0.25, h5_val))
        # denom removed; blend recomputed from displayed C/H1/H5 at row build time
        # blend now recomputed from displayed C/H1/H5 at row build time

        ss = _structure_summary_for_symbol(
            fs, sym, horizon=H5, frames_map=structure_frames
        )
        if (not isinstance(ss, dict) or not ss) and proxy_sym != sym:
            ss = _structure_summary_for_symbol(
                fs, proxy_sym, horizon=H5, frames_map=structure_frames
            )

        sup = _first_num(
            ss.get("support_cushion_atr") if isinstance(ss, dict) else None,
            ss.get("support_atr") if isinstance(ss, dict) else None,
            ss.get("sup_atr") if isinstance(ss, dict) else None,
            row.get("sup_atr"),
            proxy_row.get("sup_atr"),
            row.get("support_atr"),
            proxy_row.get("support_atr"),
        )
        res = _first_num(
            ss.get("overhead_resistance_atr") if isinstance(ss, dict) else None,
            ss.get("resistance_atr") if isinstance(ss, dict) else None,
            ss.get("res_atr") if isinstance(ss, dict) else None,
            row.get("res_atr"),
            proxy_row.get("res_atr"),
            row.get("resistance_atr"),
            proxy_row.get("resistance_atr"),
        )
        state = (
            (ss.get("state_text") if isinstance(ss, dict) else None)
            or (
                ",".join(str(x) for x in ss.get("state_tags") if x)
                if isinstance(ss, dict) and isinstance(ss.get("state_tags"), list)
                else None
            )
            or row.get("state")
            or proxy_row.get("state")
            or "-"
        )
        stop = _first_num(
            ss.get("tactical_stop_candidate") if isinstance(ss, dict) else None,
            ss.get("catastrophic_stop_candidate") if isinstance(ss, dict) else None,
            ss.get("stop") if isinstance(ss, dict) else None,
        )
        buy = _first_num(
            ss.get("stop_buy_candidate") if isinstance(ss, dict) else None,
            ss.get("breakout_trigger") if isinstance(ss, dict) else None,
            ss.get("buy") if isinstance(ss, dict) else None,
        )

        display_rows.append(
            {
                "sym": f"{sym}•" if sym in held_set else sym,
                "blend": _blend_from_components(
                    c_val,
                    _forecast_score_to_current_utility(h1_val, c_val),
                    _forecast_score_to_current_utility(h5_val, c_val),
                ),
                "c": c_val,
                "h1": _forecast_score_to_current_utility(h1_val, c_val),
                "h5": _forecast_score_to_current_utility(h5_val, c_val),
                "sup": sup,
                "res": res,
                "state": state,
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
        pad_edge=False,
    )
    tbl.add_column("Sym", justify="left", no_wrap=True)
    tbl.add_column("Blend", justify="right", no_wrap=True)
    tbl.add_column("C", justify="right", no_wrap=True)
    tbl.add_column("H1", justify="right", no_wrap=True)
    tbl.add_column("H5", justify="right", no_wrap=True)
    tbl.add_column("SupATR", justify="right", no_wrap=True)
    tbl.add_column("ResATR", justify="right", no_wrap=True)
    tbl.add_column("State", justify="left", no_wrap=True)
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
            Text(_compact_state_tags(r["state"]), style=_state_style(r["state"])),
            Text(_fmt_num(r["stop"]), style=_num_style(r["stop"])),
            Text(_fmt_num(r["buy"]), style=_num_style(r["buy"])),
        )

    console.print(
        Panel(
            tbl,
            title="Overview (expanded universe, compact tri-score) • all",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )
    return console.export_text(styles=True) + NL


def _has_structure_payload(forecast_doc, sym, horizons=(1, 5)):
    if not isinstance(forecast_doc, dict):
        return False
    scores = forecast_doc.get("scores")
    if not isinstance(scores, dict):
        return False

    by_h = scores.get(str(sym).upper())
    if not isinstance(by_h, dict):
        return False

    want_keys = {
        "structure_summary",
        "support_cushion_atr",
        "overhead_resistance_atr",
        "state_tags",
        "state_text",
        "tactical_stop_candidate",
        "catastrophic_stop_candidate",
        "stop_buy_candidate",
        "breakout_trigger",
    }

    def _walk_has(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in want_keys and v not in (None, "", [], {}):
                    return True
            return any(_walk_has(v) for v in obj.values())
        if isinstance(obj, list):
            return any(_walk_has(v) for v in obj)
        return False

    for h in horizons:
        payload = by_h.get(str(h), by_h.get(h))
        if not isinstance(payload, dict):
            return False
        if not _walk_has(payload):
            return False
    return True


def _ensure_structure_summary_payloads(
    forecast_doc,
    symbols,
    *,
    period="6mo",
    interval="1d",
    horizons=(1, 5),
):
    if not isinstance(forecast_doc, dict):
        forecast_doc = {}
    scores = forecast_doc.get("scores")
    if not isinstance(scores, dict):
        scores = {}

    syms = []
    for sym in symbols or []:
        s = str(sym or "").upper().strip()
        if s and s not in syms:
            syms.append(s)

    missing = [
        sym for sym in syms if not _has_structure_payload(forecast_doc, sym, horizons)
    ]
    if not missing:
        return forecast_doc

    try:
        from market_health.forecast_score_provider import compute_forecast_universe
    except Exception:
        return forecast_doc

    frames = _download_price_frames(["SPY", *missing], period=period, interval=interval)
    if not isinstance(frames, dict):
        return forecast_doc

    spy_ohlcv = _df_to_ohlcv(frames.get("SPY"))
    if spy_ohlcv is None:
        return forecast_doc

    universe = {"SPY": spy_ohlcv}
    for sym in missing:
        ohlcv = _df_to_ohlcv(frames.get(sym))
        if ohlcv is not None:
            universe[sym] = ohlcv

    if len(universe) <= 1:
        return forecast_doc

    try:
        horizon_tuple = tuple(int(h) for h in horizons)
    except Exception:
        horizon_tuple = (1, 5)

    calendar = {
        "schema": "calendar.v1",
        "windows": {"by_h": {str(h): {} for h in horizon_tuple}},
    }

    try:
        fresh = compute_forecast_universe(
            universe=universe,
            spy=spy_ohlcv,
            horizons_trading_days=horizon_tuple,
            calendar=calendar,
        )
    except Exception:
        return forecast_doc

    if not isinstance(fresh, dict):
        return forecast_doc

    out = dict(forecast_doc)
    out_scores = dict(scores)

    for sym in missing:
        by_h_new = fresh.get(sym)
        if not isinstance(by_h_new, dict):
            continue

        by_h_old = out_scores.get(sym)
        if not isinstance(by_h_old, dict):
            by_h_old = {}

        merged = {}
        for k, v in by_h_old.items():
            merged[str(k)] = v

        for k, v in by_h_new.items():
            hk = str(k)
            old_payload = merged.get(hk)
            if isinstance(old_payload, dict) and isinstance(v, dict):
                new_payload = dict(old_payload)
                new_payload.update(v)
                merged[hk] = new_payload
            else:
                merged[hk] = v

        out_scores[sym] = merged

    out["scores"] = out_scores
    return out


def render_my_positions_triscore_prototype(held_syms):
    import json
    from pathlib import Path

    NL = chr(10)
    cache = Path.home() / ".cache" / "jerboa"
    fs_p = cache / "forecast_scores.v1.json"

    factor_names = {
        "A": "Announcements",
        "B": "Backdrop",
        "C": "Crowding",
        "D": "Danger",
        "E": "Environment",
    }

    def _jload(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _norm(sym):
        s = str(sym or "").strip().upper()
        return s if s else ""

    def _checks_for(payload, factor):
        if not isinstance(payload, dict):
            return []
        cats = payload.get("categories")
        if not isinstance(cats, dict):
            return []
        cat = cats.get(factor)
        if not isinstance(cat, dict):
            return []
        checks = cat.get("checks")
        return checks if isinstance(checks, list) else []

    def _digit(chk):
        if isinstance(chk, dict) and isinstance(chk.get("score"), (int, float)):
            return max(0, min(2, int(chk.get("score"))))
        return 0

    def _totals(payload):
        pts = 0
        mx = 0
        if not isinstance(payload, dict):
            return None
        cats = payload.get("categories")
        if not isinstance(cats, dict):
            return None
        for factor in ("A", "B", "C", "D", "E"):
            for chk in _checks_for(payload, factor):
                pts += _digit(chk)
                mx += 2
        return int(round((pts / mx) * 100)) if mx else None

    def _factor_points(payload, factor):
        return sum(_digit(chk) for chk in _checks_for(payload, factor))

    held = []
    for s in held_syms or []:
        ns = _norm(s)
        if ns and ns not in held:
            held.append(ns)
    if not held:
        return ""

    try:
        current_rows, current_data = _unpack_scores(
            compute_scores(
                sectors=list(dict.fromkeys(["SPY", *held])),
                period="6mo",
                interval="1d",
            )
        )
    except Exception:
        current_rows, current_data = [], None

    current_map = {}
    for row in current_rows or []:
        if not isinstance(row, dict):
            continue
        sym = _norm(row.get("symbol"))
        if sym:
            current_map[sym] = row

    fs_doc = _jload(fs_p)
    try:
        fs_doc = _backfill_missing_forecast_scores(
            forecast_doc=fs_doc if isinstance(fs_doc, dict) else {},
            symbols=held,
            data=current_data,
            horizons=(1, 5),
        )
    except Exception:
        pass

    try:
        fs_doc = _ensure_forecast_payloads(
            fs_doc,
            held,
            period="6mo",
            interval="1d",
            horizons=(1, 5),
        )
    except Exception:
        pass

    scores = fs_doc.get("scores") if isinstance(fs_doc, dict) else {}
    scores = scores if isinstance(scores, dict) else {}

    horizons = fs_doc.get("horizons_trading_days") if isinstance(fs_doc, dict) else None
    if isinstance(horizons, list) and len(horizons) >= 2:
        try:
            H1 = int(horizons[0])
            H5 = int(horizons[1])
        except Exception:
            H1, H5 = 1, 5
    else:
        H1, H5 = 1, 5

    mapped = [s for s in held if s in current_map or s in scores]
    unmapped = [s for s in held if s not in mapped]
    if not mapped and not unmapped:
        return ""

    lines = []
    lines.append("")
    lines.append(
        "============================== Details (your positions) =============================="
    )
    lines.append("My Positions — Tri-Score Prototype (read-only)")
    lines.append("Each cell shows C/H1/H5 (digits 0=red, 1=yellow, 2=green).")
    lines.append(f"cache={cache}")
    lines.append(f"horizons: H1={H1}  H5={H5}")
    lines.append("")

    for sym in mapped:
        curr = current_map.get(sym, {})
        by_h = scores.get(sym, {}) if isinstance(scores.get(sym), dict) else {}
        h1_payload = by_h.get(str(H1), by_h.get(H1)) if isinstance(by_h, dict) else {}
        h5_payload = by_h.get(str(H5), by_h.get(H5)) if isinstance(by_h, dict) else {}

        cur_pct = _totals(curr)
        h1_pct = _totals(h1_payload)
        h5_pct = _totals(h5_payload)

        lines.append(
            f"== {sym} ==  Totals (C/H1/H5):"
            f" {str(cur_pct).rjust(4) + '%' if cur_pct is not None else '   -'}"
            f" {str(h1_pct).rjust(4) + '%' if h1_pct is not None else '   -'}"
            f" {str(h5_pct).rjust(4) + '%' if h5_pct is not None else '   -'}"
        )
        lines.append("")
        lines.append("Factor                1   2   3   4   5   6   Tot(C/H1/H5)")
        lines.append(
            "--------------------------------------------------------------------"
        )

        for factor in ("A", "B", "C", "D", "E"):
            cur_checks = _checks_for(curr, factor)
            h1_checks = _checks_for(h1_payload, factor)
            h5_checks = _checks_for(h5_payload, factor)

            width = max(6, len(cur_checks), len(h1_checks), len(h5_checks))
            triplets = []
            for i in range(width):
                c = _digit(cur_checks[i]) if i < len(cur_checks) else 0
                h1 = _digit(h1_checks[i]) if i < len(h1_checks) else 0
                h5 = _digit(h5_checks[i]) if i < len(h5_checks) else 0
                triplets.append(f"{c}{h1}{h5}")

            cur_pts = _factor_points(curr, factor)
            h1_pts = _factor_points(h1_payload, factor)
            h5_pts = _factor_points(h5_payload, factor)

            label = f"{factor} {factor_names[factor]}"
            lines.append(
                f"{label:<20} "
                + " ".join(f"{t:>3}" for t in triplets[:6])
                + f"  {cur_pts}/{h1_pts}/{h5_pts}"
            )

        lines.append("")
        if unmapped:
            lines.append("Unmapped (not sector ETFs): " + ", ".join(unmapped))
            lines.append("")

    if unmapped and not mapped:
        lines.append("Unmapped (not sector ETFs): " + ", ".join(unmapped))
        lines.append("")

    lines.append(
        "Note: C digit comes from current health scoring; H1/H5 digits come from forecast_scores.v1.json."
    )
    return NL.join(lines).rstrip() + NL


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


def _download_price_frames(symbols, *, period: str = "6mo", interval: str = "1d"):
    syms = [
        str(sym).upper().strip()
        for sym in (symbols or [])
        if isinstance(sym, str) and str(sym).strip()
    ]
    if not syms:
        return {}

    try:
        import yfinance as yf
    except Exception:
        return {}

    out = {}
    for sym in syms:
        try:
            df = yf.download(
                sym,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        except Exception:
            continue

        if df is None or getattr(df, "empty", True):
            continue

        # Normalize possible multi-index columns from yfinance.
        cols = getattr(df, "columns", None)
        if cols is not None and getattr(cols, "nlevels", 1) > 1:
            try:
                df = df.droplevel(-1, axis=1)
            except Exception:
                try:
                    df = df.xs(sym, axis=1, level=0)
                except Exception:
                    pass

        out[sym] = df

    return out


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

    data_map = dict(data) if isinstance(data, dict) else {}

    # Fallback: compact tri-score calls compute_scores(), which only returns rows.
    # In that path we need to fetch price frames ourselves for SPY + missing symbols.
    need_frames = ["SPY", *missing]
    need_download = [
        sym
        for sym in need_frames
        if not isinstance(data_map.get(sym), object)
        or getattr(data_map.get(sym), "empty", True)
    ]
    if need_download:
        downloaded = _download_price_frames(need_download, period="6mo", interval="1d")
        for sym, df in downloaded.items():
            data_map[str(sym).upper()] = df

    spy = _df_to_ohlcv(data_map.get("SPY"))
    if spy is None:
        doc["scores"] = scores
        doc.setdefault("horizons_trading_days", list(horizons))
        return doc

    universe = {}
    for sym in missing:
        ohlcv = _df_to_ohlcv(data_map.get(sym))
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


def _summary_display_iso_local(value):
    if not isinstance(value, str) or not value.strip():
        return "-"
    try:
        from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2

        try:
            from zoneinfo import ZoneInfo as _ZI2

            _et = _ZI2("America/New_York")
        except Exception:
            _et = _tz2(_td2(hours=-5), "ET")
        return (
            _dt2.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(_et)
            .strftime("%Y-%m-%d %I:%M:%S %p %Z")
        )
    except Exception:
        return str(value)


def _summary_display_iso_local(value):
    if not isinstance(value, str) or not value.strip():
        return "-"
    try:
        from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2

        try:
            from zoneinfo import ZoneInfo as _ZI2

            _et = _ZI2("America/New_York")
        except Exception:
            _et = _tz2(_td2(hours=-5), "ET")
        return (
            _dt2.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(_et)
            .strftime("%Y-%m-%d %I:%M:%S %p %Z")
        )
    except Exception:
        return str(value)


def _first_present(*vals):
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v
    return None


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
    _rec_src = rec_doc if isinstance(rec_doc, dict) else {}
    _rec_bucket = (
        _rec_src.get("recommendation")
        if isinstance(_rec_src.get("recommendation"), dict)
        else {}
    )
    _rec_st = (
        _rec_src.get("source_timestamps")
        if isinstance(_rec_src.get("source_timestamps"), dict)
        else {}
    )
    _bucket_st = (
        _rec_bucket.get("source_timestamps")
        if isinstance(_rec_bucket.get("source_timestamps"), dict)
        else {}
    )

    _positions_source_iso = _first_present(
        _rec_src.get("positions_source_asof"),
        _rec_bucket.get("positions_source_asof"),
        _rec_st.get("positions_source_asof"),
        _bucket_st.get("positions_source_asof"),
        _rec_src.get("positions_asof"),
        _rec_bucket.get("positions_asof"),
        _rec_st.get("positions_asof"),
        _bucket_st.get("positions_asof"),
    )
    _positions_cache_iso = _first_present(
        _rec_src.get("positions_cache_asof"),
        _rec_bucket.get("positions_cache_asof"),
        _rec_st.get("positions_cache_asof"),
        _bucket_st.get("positions_cache_asof"),
    )

    if _positions_source_iso:
        positions_display = _summary_display_iso_local(_positions_source_iso)
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
    _coherent_reco = _coherent_reco_summary_from_obj(d if isinstance(d, dict) else None)
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
    _coherent_reco_live = _coherent_reco_summary_from_obj(
        d if isinstance(d, dict) else None
    )
    _coherent_policy_live = _coherent_reco_policy_from_obj(
        d if isinstance(d, dict) else None
    )

    best_line = (
        _coherent_reco_live.get("best")
        if isinstance(_coherent_reco_live, dict) and _coherent_reco_live.get("best")
        else _comp_line(best, best_components)
    )
    _best_candidate_blend = (
        _coherent_policy_live.get("best_blend")
        if isinstance(_coherent_policy_live, dict)
        else None
    )

    _held_live = []
    _pos_doc_live = read_json(CACHE_DIR / "positions.v1.json")
    _pos_syms_live = (
        extract_symbols_from_positions(_pos_doc_live)
        if isinstance(_pos_doc_live, dict)
        else []
    )

    _held_util_live = {}
    try:
        _held_rows_live, _held_data_live = _unpack_scores(
            compute_scores(
                sectors=list(dict.fromkeys(["SPY", *_pos_syms_live])),
                period="6mo",
                interval="1d",
            )
        )
    except Exception:
        _held_rows_live, _held_data_live = ([], None)

    for _row in _held_rows_live or []:
        if not isinstance(_row, dict):
            continue
        _sym = str(_row.get("symbol") or "").strip().upper()
        _cats = _row.get("categories") or {}
        _pts = 0
        _mx = 0
        for _cat in ("A", "B", "C", "D", "E"):
            _node = _cats.get(_cat)
            if not isinstance(_node, dict):
                continue
            _checks = _node.get("checks") or []
            for _chk in _checks:
                if isinstance(_chk, dict) and isinstance(
                    _chk.get("score"), (int, float)
                ):
                    _pts += int(_chk["score"])
                    _mx += 2
        if _sym and _mx:
            _held_util_live[_sym] = round(_pts / _mx, 2)

    _seen_held = set()
    for _sym in _pos_syms_live:
        _ss = str(_sym or "").strip().upper()
        if not _ss or _ss in _seen_held:
            continue
        _seen_held.add(_ss)
        _u = _held_util_live.get(_ss)
        if _u is not None:
            _held_live.append((float(_u), _ss))

    if _held_live:
        _weakest_held_blend, _weakest_held_sym = min(
            _held_live, key=lambda t: (t[0], t[1])
        )
    else:
        _weakest_held_blend, _weakest_held_sym = (None, weakest)

    _fs_doc_live = read_json(CACHE_DIR / "forecast_scores.v1.json")
    _scores_live = _fs_doc_live.get("scores") if isinstance(_fs_doc_live, dict) else {}
    _scores_live = _scores_live if isinstance(_scores_live, dict) else {}

    def _payload_pct(_payload):
        if not isinstance(_payload, dict):
            return None
        _cats = _payload.get("categories")
        if not isinstance(_cats, dict):
            return None
        _pts = 0
        _mx = 0
        for _cat in ("A", "B", "C", "D", "E"):
            _node = _cats.get(_cat)
            if not isinstance(_node, dict):
                continue
            _checks = _node.get("checks") or []
            for _chk in _checks:
                if isinstance(_chk, dict) and isinstance(
                    _chk.get("score"), (int, float)
                ):
                    _pts += int(_chk["score"])
                    _mx += 2
        return round(_pts / _mx, 2) if _mx else None

    def _fmt_live(_v):
        return "-" if _v is None else f"{float(_v):.2f}"

    _by_h_live = (
        _scores_live.get(_weakest_held_sym, {})
        if isinstance(_scores_live.get(_weakest_held_sym), dict)
        else {}
    )
    _h1_live = _payload_pct(_by_h_live.get("1", _by_h_live.get(1)))
    _h5_live = _payload_pct(_by_h_live.get("5", _by_h_live.get(5)))
    _c_live = _weakest_held_blend
    if _c_live is not None and _h1_live is not None and _h5_live is not None:
        _blend_live = round((0.50 * _c_live) + (0.25 * _h1_live) + (0.25 * _h5_live), 2)
    else:
        _blend_live = _c_live

    weakest_line = (
        f"{_weakest_held_sym}  (blend {_fmt_live(_blend_live)} | "
        f"C {_fmt_live(_c_live)} | H1 {_fmt_live(_h1_live)} | H5 {_fmt_live(_h5_live)})"
    )

    delta = _num(d.get("delta_utility"))
    if (
        _best_candidate_blend is not None
        and "_blend_live" in locals()
        and _blend_live is not None
    ):
        delta = round(float(_best_candidate_blend) - float(_blend_live), 2)
    elif _best_candidate_blend is not None and _weakest_held_blend is not None:
        delta = round(float(_best_candidate_blend) - float(_weakest_held_blend), 2)
    if isinstance(_coherent_reco, dict) and _coherent_reco.get("delta") is not None:
        delta = _coherent_reco.get("delta")
    thr = _num(d.get("threshold"))
    shortfall = (thr - delta) if (delta is not None and thr is not None) else None

    _coherent_policy = _coherent_reco_policy_from_obj(
        d if isinstance(d, dict) else None
    )
    _best_blend = (
        _coherent_policy.get("best_blend")
        if isinstance(_coherent_policy, dict)
        else None
    )
    _all_blocked = bool((_coherent_policy or {}).get("all_blocked"))
    _status_count = int((_coherent_policy or {}).get("status_count") or 0)
    _min_floor = 0.55

    if _all_blocked:
        action = "NOOP"
        shortfall = None
        if _status_count > 0:
            reason = "All displayed candidates remain blocked; hold."
    elif _best_blend is not None and _best_blend < _min_floor:
        action = "NOOP"
        reason = f"No candidate clears min floor ({_min_floor:.3f}); hold."
    elif delta is not None and thr is not None and delta < thr:
        action = "NOOP"
        reason = f"No candidate clears threshold ({thr:.3f}); hold."

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
    _metric_live = str(d.get("decision_metric") or metric or "")
    _selected_pair_live = (
        d.get("selected_pair") if isinstance(d.get("selected_pair"), dict) else {}
    )
    _best_label = "best candidate"
    _from_label = "weakest held"
    from_line = weakest_line
    _delta_header = delta
    _reason_header = str(reason)
    _shortfall_header = shortfall

    if "robust_edge" in _metric_live and isinstance(_selected_pair_live, dict):
        _best_sym_live = (
            str(_selected_pair_live.get("to_symbol") or best or "").strip().upper()
        )
        _from_sym_live = (
            str(_selected_pair_live.get("from_symbol") or weakest or "").strip().upper()
        )

        if _best_sym_live:
            _best_comp_live = _merge_comp(
                _best_sym_live,
                candidate_components
                if isinstance(candidate_components, dict)
                else None,
            )
            best_line = _comp_line(_best_sym_live, _best_comp_live)

        if _from_sym_live:
            _from_comp_live = _merge_comp(
                _from_sym_live,
                held_components.get(_from_sym_live)
                if isinstance(held_components, dict)
                else None,
            )
            from_line = _comp_line(_from_sym_live, _from_comp_live)

        _from_label = "selected from"

        _weighted_live = _num(_selected_pair_live.get("weighted_robust_edge"))
        _robust_live = _num(_selected_pair_live.get("robust_edge"))

        if _metric_live == "portfolio_weighted_robust_edge":
            _delta_header = (
                _weighted_live
                if _weighted_live is not None
                else (_robust_live if _robust_live is not None else delta)
            )
        else:
            _delta_header = _robust_live if _robust_live is not None else delta

        _vetoed_live = bool(_selected_pair_live.get("vetoed"))
        _veto_reason_live = str(_selected_pair_live.get("veto_reason") or "").strip()

        if _vetoed_live and _veto_reason_live:
            _reason_header = f"Forecast veto: {_veto_reason_live}"
            _shortfall_header = None
        elif thr is not None and _delta_header is not None:
            _shortfall_header = max(0.0, float(thr) - float(_delta_header))
            if action == "NOOP":
                _reason_header = (
                    f"No candidate clears threshold "
                    f"(best={float(_delta_header):.3f} < {float(thr):.3f}); hold."
                )
            else:
                _reason_header = str(reason)
        else:
            _shortfall_header = None

    _rec_src = rec_doc if isinstance(rec_doc, dict) else {}
    _rec_bucket = (
        _rec_src.get("recommendation")
        if isinstance(_rec_src.get("recommendation"), dict)
        else {}
    )
    _rec_st = (
        _rec_src.get("source_timestamps")
        if isinstance(_rec_src.get("source_timestamps"), dict)
        else {}
    )
    _bucket_st = (
        _rec_bucket.get("source_timestamps")
        if isinstance(_rec_bucket.get("source_timestamps"), dict)
        else {}
    )

    _positions_source_display = _summary_display_iso_local(
        _rec_bucket.get("positions_source_asof")
        or _rec_src.get("positions_source_asof")
        or _bucket_st.get("positions_source_asof")
        or _rec_st.get("positions_source_asof")
        or d.get("positions_source_asof")
        or ((d.get("source_timestamps") or {}).get("positions_source_asof"))
        or _rec_bucket.get("positions_asof")
        or _rec_src.get("positions_asof")
        or _bucket_st.get("positions_asof")
        or _rec_st.get("positions_asof")
        or d.get("positions_asof")
        or ((d.get("source_timestamps") or {}).get("positions_asof"))
    )
    _positions_cache_display = _summary_display_iso_local(
        _rec_bucket.get("positions_cache_asof")
        or _rec_src.get("positions_cache_asof")
        or _bucket_st.get("positions_cache_asof")
        or _rec_st.get("positions_cache_asof")
        or d.get("positions_cache_asof")
        or ((d.get("source_timestamps") or {}).get("positions_cache_asof"))
    )

    summary.add_row("positions", str(_positions_source_display))
    if (
        _positions_cache_display not in {"", "-"}
        and _positions_cache_display != _positions_source_display
    ):
        summary.add_row("positions cache", str(_positions_cache_display))
    summary.add_row("forecast", str(forecast_display))
    summary.add_row("computed", str(computed_display))
    summary.add_row("fresh", str(freshness_line))
    summary.add_row("age p/f/s", str(age_display))
    summary.add_row("skew", str(skew_display))
    summary.add_row("fp", str(fp))
    summary.add_row("action", Text(action, style=action_style))
    summary.add_row("metric", str(metric))
    summary.add_row("weights", str(weights))
    summary.add_row("why", str(_reason_header))
    summary.add_row(_best_label, Text(best_line, style="bold green"))
    summary.add_row(_from_label, Text(from_line, style="bold yellow"))
    summary.add_row(
        "delta",
        Text(_fmt(_delta_header), style=_delta_style(_delta_header, thr)),
    )
    summary.add_row("threshold", Text(_fmt(thr), style="cyan"))
    if _shortfall_header is not None and float(_shortfall_header) > 0:
        summary.add_row("shortfall", Text(_fmt(_shortfall_header), style="yellow"))

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
        tbl.add_column("Edge", justify="right", no_wrap=True)
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
                    _fmt(
                        row.get("decision_value")
                        if row.get("decision_value") is not None
                        else row.get("delta_blended")
                    ),
                    style=_delta_style(
                        row.get("decision_value")
                        if row.get("decision_value") is not None
                        else row.get("delta_blended"),
                        thr,
                    ),
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
                    row["h1"] = _forecast_score_to_current_utility(
                        h1_score, current_utility
                    )

                if isinstance(h5_score, (int, float)):
                    row["h5_utility"] = float(h5_score)
                    row["h5"] = _forecast_score_to_current_utility(
                        h5_score, current_utility
                    )

                if isinstance(h1_score, (int, float)) and isinstance(
                    h5_score, (int, float)
                ):
                    blended = _blend_from_components(
                        row.get("c"), row.get("h1"), row.get("h5")
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
    tri_overview = render_overview_triscore(overview_order, util, held_syms)
    if tri_overview:
        sys.stdout.write(tri_overview + chr(10))

    tri_details = render_my_positions_triscore_prototype(held_syms)
    if tri_details:
        sys.stdout.write(tri_details + chr(10))
    else:
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
