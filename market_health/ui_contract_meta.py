# Dimension display names come from ui.v1 contract metadata (no hardcoded UI strings).
# Reads ~/.cache/jerboa/market_health.ui.v1.json by default (or $JERBOA_UI_JSON).

from __future__ import annotations

_DIM_META_CACHE = None

def _load_dimensions_meta():
    global _DIM_META_CACHE
    if _DIM_META_CACHE is not None:
        return _DIM_META_CACHE
    try:
        import json, os
        from pathlib import Path
        ui_json = os.environ.get("JERBOA_UI_JSON", "~/.cache/jerboa/market_health.ui.v1.json")
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
