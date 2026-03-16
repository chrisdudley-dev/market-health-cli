import json
import os
from datetime import datetime, timezone
from pathlib import Path
from market_health.universe import get_asset_meta

out_json = Path(os.path.expanduser("~/.cache/jerboa/market_health.ui.v1.json"))
out_json.parent.mkdir(parents=True, exist_ok=True)
state_p = Path(
    os.path.expanduser("~/.cache/jerboa/state/market_health_refresh_all.state.json")
)
env_p = Path(os.path.expanduser("~/.cache/jerboa/environment.v1.json"))
sect_p = Path(os.path.expanduser("~/.cache/jerboa/market_health.sectors.json"))
pos_p = Path(os.path.expanduser("~/.cache/jerboa/positions.v1.json"))


def read_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8", errors="replace"))
    except Exception:
        return {"_error": "unreadable", "_path": str(p)}


def meta(p: Path):
    if not p.exists():
        return {"path": str(p), "exists": False, "mtime": 0, "bytes": 0}
    st = p.stat()
    return {
        "path": str(p),
        "exists": True,
        "mtime": int(st.st_mtime),
        "bytes": int(st.st_size),
    }


def enrich_sector_rows(obj):
    if not isinstance(obj, list):
        return obj
    out = []
    for row in obj:
        if not isinstance(row, dict):
            out.append(row)
            continue
        sym = row.get("symbol")
        if not isinstance(sym, str) or not sym.strip():
            out.append(row)
            continue
        meta_obj = get_asset_meta(sym)
        new_row = dict(row)
        new_row.setdefault("asset_type", meta_obj.asset_type)
        new_row.setdefault("group", meta_obj.group)
        new_row.setdefault("metal_type", meta_obj.metal_type)
        new_row.setdefault("is_basket", meta_obj.is_basket)
        out.append(new_row)
    return out


def recommendation_summary_blob(rec_blob):
    out = {
        "action": None,
        "reason": None,
        "fallback_reason": None,
        "has_candidate_rows": False,
    }
    if not isinstance(rec_blob, dict):
        return out
    rec = rec_blob.get("recommendation")
    if not isinstance(rec, dict):
        rec = rec_blob if isinstance(rec_blob, dict) else {}
    if not isinstance(rec, dict):
        return out
    out["action"] = rec.get("action")
    out["reason"] = rec.get("reason")
    diag = rec.get("diagnostics")
    if isinstance(diag, dict):
        cand = diag.get("candidate_rows")
        out["has_candidate_rows"] = isinstance(cand, list) and len(cand) > 0
        out["fallback_reason"] = diag.get("fallback_reason")
    if out["fallback_reason"] is None and out["action"] == "NOOP":
        out["fallback_reason"] = out["reason"]
    return out


def status_line_fallback(state: dict | None) -> str:
    if not isinstance(state, dict):
        return "market-health: STATE missing"
    chg = state.get("changed") or {}
    rc = state.get("rc") or {}
    return (
        "market-health:"
        f" status={state.get('status', '?')}"
        f" reason={state.get('reason', '?')}"
        f" changed(mkt,pos)={chg.get('market', '?')},{chg.get('positions', '?')}"
        f" rc(mkt,pos)={rc.get('market', '?')},{rc.get('positions', '?')}"
        f" forced={state.get('forced', False)}"
    )


# Prefer the existing status command if present (so banner + UI match exactly)
status_cmd = os.path.expanduser("~/bin/jerboa-market-health-status")
status_line = None
if os.path.exists(status_cmd) and os.access(status_cmd, os.X_OK):
    try:
        import subprocess

        status_line = subprocess.check_output([status_cmd], text=True).strip()
    except Exception:
        status_line = None

state = read_json(state_p)
env = read_json(env_p)
sect = read_json(sect_p)
pos = read_json(pos_p)

if isinstance(sect, list):
    sect = enrich_sector_rows(sect)

rec = None
rec_summary = recommendation_summary_blob(rec)

if not status_line:
    status_line = status_line_fallback(state)

# Small derived summary (safe / schema-agnostic)
pos_list = []
if isinstance(pos, dict) and isinstance(pos.get("positions"), list):
    pos_list = pos["positions"]

symbols = []
for item in pos_list:
    if isinstance(item, dict):
        sym = item.get("symbol") or item.get("underlying") or item.get("ticker")
        if isinstance(sym, str) and sym and sym not in symbols:
            symbols.append(sym)
    if len(symbols) >= 12:
        break


# --- Category A: events/catalysts provider boundary (graceful) ---
ev_cfg_p = Path(os.path.expanduser("~/.config/jerboa/event_provider.json"))

events = {
    "schema": "events.v1",
    "status": "no_provider",
    "generated_at": "",
    "source": {"type": "null"},
    "points": [],
    "errors": [],
}
try:
    from market_health.providers.event_provider import load_event_provider  # type: ignore

    evp = load_event_provider()
    seed = symbols[:50] if symbols else ["SPY"]
    evb = evp.get_events(seed)
    events = {
        "schema": evb.schema,
        "status": evb.status,
        "generated_at": evb.generated_at,
        "source": evb.source,
        "points": [
            {
                "ts": pt.ts,
                "symbol": pt.symbol,
                "type": pt.type,
                "headline": pt.headline,
                "impact": pt.impact,
                "confidence": pt.confidence,
                "extra": pt.extra,
            }
            for pt in evb.points
        ],
        "errors": evb.errors,
    }
except Exception:
    events = {
        "schema": "events.v1",
        "status": "error",
        "generated_at": "",
        "source": {"type": "error"},
        "points": [],
        "errors": [],
    }

events_list = (
    events.get("points")
    if isinstance(events, dict) and isinstance(events.get("points"), list)
    else []
)

DIMENSIONS_META = {
    "A": {
        "display_name": "Announcements",
        "subtitle": "Catalysts / News / Macro",
        "description": "Catalysts/events/news/earnings/macro drivers.",
    },
    "B": {
        "display_name": "Backdrop",
        "subtitle": "Regime / Environment",
        "description": "Environment/regime context (trend, conditions).",
    },
    "C": {
        "display_name": "Crowding",
        "subtitle": "Flow / Positioning",
        "description": "Flow/positioning/participation; who is in the trade.",
    },
    "D": {
        "display_name": "Danger",
        "subtitle": "Risk / Vol / Correlation",
        "description": "Risk/volatility/correlation stress signals.",
    },
    "E": {
        "display_name": "Environment",
        "subtitle": "Macro / Regime",
        "description": "Macro/regime drivers (SPY trend, sector rank, breadth, VIX).",
    },
}
payload = {
    "schema": "jerboa.market_health.ui.v1",
    "dimensions_meta": DIMENSIONS_META,
    "categories_meta": DIMENSIONS_META,
    "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "status_line": status_line,
    "meta": {
        "state": meta(state_p),
        "environment": meta(env_p),
        "sectors": meta(sect_p),
        "positions": meta(pos_p),
        "events_provider": meta(ev_cfg_p),
    },
    "summary": {
        "symbols_sample": symbols,
        "positions_count": len(pos_list),
        "recommendation_action": rec_summary.get("action"),
        "recommendation_reason": rec_summary.get("reason"),
        "events_count": len(events_list),
        "events_status": (
            events.get("status", "?") if isinstance(events, dict) else "?"
        ),
    },
    # Keep full data for now (still one file); React reads just what it needs.
    "data": {
        "state": state,
        "environment": env,
        "sectors": sect,
        "positions": pos,
        "recommendation_summary": rec_summary,
        "events": events,
    },
}

new = json.dumps(payload, indent=2, sort_keys=True) + "\n"

# Idempotent write (don’t rewrite if identical)
old = None
try:
    old = out_json.read_text("utf-8")
except FileNotFoundError:
    old = None
except Exception:
    old = None

if old == new:
    raise SystemExit(0)

tmp = out_json.with_suffix(out_json.suffix + ".tmp")
tmp.write_text(new, "utf-8")
tmp.replace(out_json)
