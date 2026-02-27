"""market_health.positions_sectorize

Map arbitrary holdings into the sector-ETF universe (XLB..XLY) via a local overrides file.

- No network I/O
- No DB dependency
- Uses ~/.config/jerboa/symbol_sector_overrides.json when present
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


DEFAULT_OVERRIDES_PATH = os.path.expanduser(
    "~/.config/jerboa/symbol_sector_overrides.json"
)


def _read_overrides(path: str = DEFAULT_OVERRIDES_PATH) -> Dict[str, str]:
    try:
        p = Path(path)
        if not p.exists():
            return {}
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return {}
        out: Dict[str, str] = {}
        for k, v in obj.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                out[k.strip().upper()] = v.strip().upper()
        return out
    except Exception:
        return {}


def _sym_from_position_item(item: Any) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    sym = item.get("symbol") or item.get("ticker") or item.get("underlying")
    if isinstance(sym, str) and sym.strip():
        return sym.strip().upper()
    return None


def _value_from_position_item(item: Any) -> float:
    if not isinstance(item, dict):
        return 0.0
    for k in ("market_value", "marketValue", "market_value_usd", "value"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return 0.0


def sectorize_positions(
    positions: Any,
    universe: Set[str],
    *,
    overrides_path: str = DEFAULT_OVERRIDES_PATH,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (positions_sectorized, meta).

    Output is positions.v1-like:
      {"schema":"positions.v1","positions":[{"symbol":"XLK","market_value":...}, ...]}

    meta:
      - mapped: original symbols mapped
      - unmapped: originals ignored
      - mode: "sectorized" or "raw"
    """
    uni = {u.upper() for u in universe if isinstance(u, str)}
    overrides = _read_overrides(overrides_path)

    mapped: List[str] = []
    unmapped: List[str] = []
    agg: Dict[str, float] = {}

    plist = []
    if isinstance(positions, dict) and isinstance(positions.get("positions"), list):
        plist = positions["positions"]
    elif isinstance(positions, (list, tuple, set)):
        plist = [{"symbol": str(x)} for x in positions]

    for item in plist:
        sym = _sym_from_position_item(item)
        if not sym:
            continue
        val = _value_from_position_item(item)
        if val <= 0:
            val = 1.0

        target = None

        # already in universe
        if sym in uni:
            target = sym
        else:
            # exact override
            if sym in overrides:
                target = overrides[sym]
            else:
                # option-like: use underlying before "_"
                if "_" in sym:
                    und = sym.split("_", 1)[0]
                    if und in overrides:
                        target = overrides[und]

        if target and target in uni:
            agg[target] = agg.get(target, 0.0) + val
            mapped.append(sym)
        else:
            unmapped.append(sym)

    out_positions = [
        {"symbol": k, "market_value": float(v)} for k, v in sorted(agg.items())
    ]
    out = {"schema": "positions.v1", "positions": out_positions}
    meta = {
        "mode": "sectorized",
        "mapped": sorted(set(mapped)),
        "unmapped": sorted(set(unmapped)),
    }
    return out, meta
