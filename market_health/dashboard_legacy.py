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


def _forecast_score_to_current_utility(forecast_score, current_utility):
    try:
        fs = float(forecast_score)
    except Exception:
        return None
    if abs(fs) > 1.000001:
        fs = fs / 100.0
    return max(0.0, min(1.0, fs))


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

    fallback_stop = recent_low - (0.25 * atr_last)
    fallback_buy = recent_high + (0.25 * atr_last)
    stop = fallback_stop
    buy = fallback_buy
    stop_source = "recent_low_atr_fallback"
    buy_source = "recent_high_atr_fallback"

    try:
        from market_health.stop_buy_levels import (
            generate_stop_buy_candidates,
            strongest_stop_buy_clusters,
        )

        ohlcv_df = next(
            (
                value
                for value in locals().values()
                if hasattr(value, "columns")
                and hasattr(value, "empty")
                and "Close" in value.columns
            ),
            None,
        )

        if ohlcv_df is not None:
            candidates = generate_stop_buy_candidates(ohlcv_df)
            clusters = strongest_stop_buy_clusters(
                candidates,
                current_price=last_close,
                atr=atr_last,
                min_cluster_size=2,
            )
            floor_cluster = clusters.get("floor")
            ceiling_cluster = clusters.get("ceiling")

            if floor_cluster is not None:
                stop = float(floor_cluster["lower"]) - (0.25 * atr_last)
                stop_source = "clustered_floor"

            if ceiling_cluster is not None:
                buy = float(ceiling_cluster["upper"]) + (0.25 * atr_last)
                buy_source = "clustered_ceiling"
    except Exception:
        stop = fallback_stop
        buy = fallback_buy
        stop_source = "recent_low_atr_fallback"
        buy_source = "recent_high_atr_fallback"

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
        "stop_source": stop_source,
        "buy_source": buy_source,
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
    import json
    from pathlib import Path

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


def main():
    if any(flag in sys.argv for flag in ("--demo", "--json")):
        from market_health.market_ui import main as render_main

        return render_main()
    from market_health.policy_cli import main as policy_main

    return policy_main()


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
