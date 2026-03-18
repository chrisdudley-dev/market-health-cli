import json
import os
from datetime import datetime, timezone
from pathlib import Path
from market_health.market_catalog import get_symbol_meta

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
        meta_obj = get_symbol_meta(sym.strip().upper())
        new_row = dict(row)
        if meta_obj is not None:
            new_row.setdefault("market", meta_obj.market)
            new_row.setdefault("region", meta_obj.region)
            new_row.setdefault("kind", meta_obj.kind)
            new_row.setdefault("bucket_id", meta_obj.bucket_id)
            new_row.setdefault("family_id", meta_obj.family_id)
            new_row.setdefault("benchmark_symbol", meta_obj.benchmark_symbol)
            new_row.setdefault("calendar_id", meta_obj.calendar_id)
            new_row.setdefault("currency", meta_obj.currency)
            new_row.setdefault("taxonomy", meta_obj.taxonomy)
        out.append(new_row)
    return out


def summarize_market_mix(sectors, symbols_sample):
    markets = set()
    regions = set()

    if isinstance(sectors, list):
        for row in sectors:
            if isinstance(row, dict):
                m = row.get("market")
                r = row.get("region")
                if isinstance(m, str) and m.strip():
                    markets.add(m.strip().upper())
                if isinstance(r, str) and r.strip():
                    regions.add(r.strip().upper())

    if isinstance(symbols_sample, list):
        for row in symbols_sample:
            if isinstance(row, dict):
                m = row.get("market")
                r = row.get("region")
                if isinstance(m, str) and m.strip():
                    markets.add(m.strip().upper())
                if isinstance(r, str) and r.strip():
                    regions.add(r.strip().upper())

    return {
        "markets_present": sorted(markets),
        "regions_present": sorted(regions),
        "mixed_markets": len(markets) > 1,
    }


# JP_LIVE_PIVOT_EARLY_SYMBOLS_SAMPLE_META


# JP_LIVE_PIVOT_EARLY_SYMBOLS_SAMPLE_META
def symbols_sample_meta(symbols):
    out = []
    seen = set()
    for sym in symbols or []:
        if not isinstance(sym, str):
            continue
        meta = get_symbol_meta(sym)
        if meta is None:
            continue
        if str(meta.market).upper() in {"US", "USA"}:
            continue
        if meta.symbol in seen:
            continue
        out.append(
            {
                "symbol": meta.symbol,
                "market": meta.market,
                "region": meta.region,
                "kind": meta.kind,
                "bucket_id": meta.bucket_id,
                "family_id": meta.family_id,
                "benchmark_symbol": meta.benchmark_symbol,
                "calendar_id": meta.calendar_id,
                "currency": meta.currency,
                "taxonomy": meta.taxonomy,
            }
        )
        seen.add(meta.symbol)
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

sample_meta = symbols_sample_meta(symbols)
market_mix = summarize_market_mix(sect, sample_meta)


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
        "symbols_sample_meta": sample_meta,
        "markets_present": market_mix["markets_present"],
        "regions_present": market_mix["regions_present"],
        "mixed_markets": market_mix["mixed_markets"],
        "positions_count": len(pos_list),
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
