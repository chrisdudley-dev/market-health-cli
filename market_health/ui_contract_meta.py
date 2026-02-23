# Dimension display names come from ui.v1 contract metadata (no hardcoded UI strings).
# Reads ~/.cache/jerboa/market_health.ui.v1.json by default (or $JERBOA_UI_JSON).

from __future__ import annotations


# v1: canonical dimension metadata (A-F). Kept stable by tests.
DIMENSIONS_META_V1: dict[str, dict[str, str]] = {
    "A": {
        "display_name": "Narrative",
        "description": "News/analysts/events/insiders/peers/guidance context.",
    },
    "B": {
        "display_name": "Trend",
        "description": "Trend/momentum signals (MAs, relative strength, breaks).",
    },
    "C": {
        "display_name": "Flow",
        "description": "Flow/positioning (open interest, blocks, leadership breadth).",
    },
    "D": {
        "display_name": "Risk",
        "description": "Risk/volatility inputs (ATR/IV/correlation/event risk/sizing).",
    },
    "E": {
        "display_name": "Regime",
        "description": "Macro/regime drivers (SPY trend, sector rank, breadth, VIX).",
    },
    "F": {
        "display_name": "Plan",
        "description": "Execution plan (trigger, invalidation, targets, time stop).",
    },
}


def dimensions_meta_v1() -> dict[str, dict[str, str]]:
    # Return a copy to avoid accidental mutation.
    return {k: dict(v) for k, v in DIMENSIONS_META_V1.items()}


def dimension_display_name(
    key: str, meta: dict[str, dict[str, str]] | None = None
) -> str:
    m = meta or DIMENSIONS_META_V1
    return (m.get(key) or {}).get("display_name") or key


def dimension_tooltip(key: str, meta: dict[str, dict[str, str]] | None = None) -> str:
    m = meta or DIMENSIONS_META_V1
    return (m.get(key) or {}).get("description") or ""


_DIM_META_CACHE = None


def _load_dimensions_meta():
    global _DIM_META_CACHE
    if _DIM_META_CACHE is not None:
        return _DIM_META_CACHE
    try:
        import json
        import os
        from pathlib import Path

        ui_json = os.environ.get(
            "JERBOA_UI_JSON", "~/.cache/jerboa/market_health.ui.v1.json"
        )
        p = Path(os.path.expanduser(ui_json))
        d = json.loads(p.read_text("utf-8"))
        meta = d.get("dimensions_meta") or d.get("categories_meta") or {}
        _DIM_META_CACHE = meta if isinstance(meta, dict) else {}
    except Exception:
        _DIM_META_CACHE = {}
    return _DIM_META_CACHE


def dimension_heading(code: str) -> str:
    meta = _load_dimensions_meta()
    name = ""
    if isinstance(meta, dict):
        m = meta.get(code)
        if isinstance(m, dict):
            name = m.get("display_name") or ""
    return f"{code}  {name}" if name else code
