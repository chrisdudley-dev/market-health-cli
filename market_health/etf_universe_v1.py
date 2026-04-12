from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_ETFS: list[dict[str, Any]] = [
    {
        "symbol": "IBIT",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "BITI",
        "enabled": True,
        "inverse_or_levered": True,
        "strategy_wrapper": False,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "SBIT",
        "enabled": True,
        "inverse_or_levered": True,
        "strategy_wrapper": False,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "BTCI",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "QYLD",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "equity_income",
    },
    {
        "symbol": "JEPI",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "equity_income",
    },
    {
        "symbol": "BLOK",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "blockchain",
    },
    {
        "symbol": "BITC",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "ETHA",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "ethereum",
    },
    {
        "symbol": "BKCH",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "blockchain",
    },
]

ENV_VAR = "JERBOA_ETF_UNIVERSE_JSON"


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_etf_universe(
    path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Load ETF config.

    Only reads from disk if:
      - `path` is provided, OR
      - env var JERBOA_ETF_UNIVERSE_JSON is set.

    Otherwise returns DEFAULT_ETFS (deterministic for tests/CI).
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
        if isinstance(doc, dict) and isinstance(doc.get("symbols"), list):
            return [x for x in doc["symbols"] if isinstance(x, dict)]
        if isinstance(doc, list):
            return [x for x in doc if isinstance(x, dict)]

    return list(DEFAULT_ETFS)
