import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from market_health.ui_contract_meta import DIMENSIONS_META_V1

out_json = Path(os.path.expanduser("~/.cache/jerboa/market_health.ui.v1.json"))
out_json.parent.mkdir(parents=True, exist_ok=True)
state_p = Path(
    os.path.expanduser("~/.cache/jerboa/state/market_health_refresh_all.state.json")
)
env_p = Path(os.path.expanduser("~/.cache/jerboa/environment.v1.json"))
sect_p = Path(os.path.expanduser("~/.cache/jerboa/market_health.sectors.json"))
pos_p = Path(os.path.expanduser("~/.cache/jerboa/positions.v1.json"))
rec_p = Path(os.path.expanduser("~/.cache/jerboa/recommendations.v1.json"))
forecast_p = Path(os.path.expanduser("~/.cache/jerboa/forecast_scores.v1.json"))


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
        status_line = subprocess.check_output([status_cmd], text=True).strip()
    except Exception:
        status_line = None

state = read_json(state_p)
env = read_json(env_p)
sect = read_json(sect_p)
pos = read_json(pos_p)
rec_raw = read_json(rec_p)
forecast_raw = read_json(forecast_p)

rec_status = "ok"
rec = rec_raw
if rec_raw is None:
    rec_status = "missing"
    rec = None
elif isinstance(rec_raw, dict) and rec_raw.get("_error"):
    rec_status = "unreadable"
    rec = None

forecast_status = "ok"
forecast = forecast_raw
if forecast_raw is None:
    forecast_status = "missing"
    forecast = None
elif isinstance(forecast_raw, dict) and forecast_raw.get("_error"):
    forecast_status = "unreadable"
    forecast = None

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
        "recommendations": meta(rec_p),
        "forecast_scores": meta(forecast_p),
        "events_provider": meta(ev_cfg_p),
    },
    "summary": {
        "symbols_sample": symbols,
        "positions_count": len(pos_list),
        "recommendations_status": rec_status,
        "forecast_scores_status": forecast_status,
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
        "dimensions_meta": DIMENSIONS_META_V1,
        "recommendations": rec,
        "forecast_scores": forecast,
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
