from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Deterministic default for tests/CI.
DEFAULT_PAIRS: list[dict[str, Any]] = [
    {"sector_id": "TECH", "long": "XLK", "inverse": "TECS", "inverse_leverage": -3},
    {"sector_id": "FIN", "long": "XLF", "inverse": "FAZ", "inverse_leverage": -3},
    {"sector_id": "ENERGY", "long": "XLE", "inverse": "ERY", "inverse_leverage": -2},
    {"sector_id": "RE", "long": "XLRE", "inverse": "DRV", "inverse_leverage": -3},
    {"sector_id": "IND", "long": "XLI", "inverse": "SIJ", "inverse_leverage": -2},
    {"sector_id": "MAT", "long": "XLB", "inverse": "SMN", "inverse_leverage": -2},
    {"sector_id": "UTIL", "long": "XLU", "inverse": "SDP", "inverse_leverage": -2},
    {"sector_id": "STAP", "long": "XLP", "inverse": "SZK", "inverse_leverage": -2},
    {"sector_id": "HC", "long": "XLV", "inverse": "RXD", "inverse_leverage": -2},
    {"sector_id": "DISC", "long": "XLY", "inverse": "SCC", "inverse_leverage": -2},
]

ENV_VAR = "JERBOA_INVERSE_UNIVERSE_JSON"


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_inverse_pairs(
    path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Load inverse pairs.

    Only reads from disk if:
      - `path` is provided, OR
      - env var JERBOA_INVERSE_UNIVERSE_JSON is set.

    Otherwise returns DEFAULT_PAIRS (deterministic for tests/CI).
    """
    p: Path | None = None
    if path:
        p = Path(path).expanduser()
    else:
        env = os.environ.get(ENV_VAR)
        if env:
            p = Path(env).expanduser()

    if p and p.exists():
        doc = _read_json(p)
        if isinstance(doc, dict) and isinstance(doc.get("pairs"), list):
            return [x for x in doc["pairs"] if isinstance(x, dict)]
        if isinstance(doc, list):
            return [x for x in doc if isinstance(x, dict)]

    return list(DEFAULT_PAIRS)
