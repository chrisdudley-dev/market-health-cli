"""
Market Health public API.

- compute_scores(...)  -> programmatic access to sector rows
- SECTORS_DEFAULT      -> exported if present in engine.py
- CHECK_LABELS         -> exported if present in engine.py
"""

from __future__ import annotations
from typing import Any, Optional

__version__ = "0.2.0"

# Lazy, safe import: only catch ImportError (not all exceptions).
try:
    from . import engine as _engine  # type: ignore
except ImportError:
    _engine = None  # type: ignore

# Soft-exports (only if engine provides them)
SECTORS_DEFAULT: Optional[Any] = getattr(_engine, "SECTORS_DEFAULT", None) if _engine else None
CHECK_LABELS:   Optional[Any] = getattr(_engine, "CHECK_LABELS",   None) if _engine else None


def compute_scores(
        sectors=None,
        period: str = "1y",
        interval: str = "1d",
        ttl: int = 300,
        *,
        demo: bool = False,
        json_path: str | None = None,
        seed: int = 42,
):
    """
    Return a list of SectorRow-like objects from the engine.

    Calls functions in engine.py if they exist:
      - build_demo_dataset(sectors, seed)
      - load_json_dataset(json_path, sectors)
      - load_live_dataset(sectors, period, interval, ttl)
    """
    if _engine is None:
        raise ImportError("market_health.engine could not be imported")

    # Determine sector list (fallback to engine default if available)
    if sectors is None:
        sectors = getattr(_engine, "SECTORS_DEFAULT", None)
    if sectors is None:
        raise ValueError("No sectors provided and SECTORS_DEFAULT not found in engine.py")

    if demo:
        fn = getattr(_engine, "build_demo_dataset", None)
        if fn is None:
            raise NotImplementedError("engine.build_demo_dataset(...) is missing")
        return fn(sectors, seed=seed)

    if json_path:
        fn = getattr(_engine, "load_json_dataset", None)
        if fn is None:
            raise NotImplementedError("engine.load_json_dataset(...) is missing")
        return fn(json_path, sectors)

    fn = getattr(_engine, "load_live_dataset", None)
    if fn is None:
        raise NotImplementedError("engine.load_live_dataset(...) is missing")
    return fn(sectors, period, interval, ttl)


__all__ = ["compute_scores", "SECTORS_DEFAULT", "CHECK_LABELS", "__version__"]
