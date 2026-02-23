"""
Market Health public API.

- compute_scores(...)  -> programmatic access to sector rows
- SECTORS_DEFAULT      -> exported if present in engine.py
- CHECK_LABELS         -> exported if present in engine.py
"""

from __future__ import annotations
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("market-health-cli")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0+unknown"
from typing import Any, Optional

# (removed old __version__ line)
# Lazy, safe import: only catch ImportError (not all exceptions).
try:
    from . import engine as _engine  # type: ignore
except ImportError:
    _engine = None  # type: ignore

# Soft-exports (only if engine provides them)
SECTORS_DEFAULT: Optional[Any] = (
    getattr(_engine, "SECTORS_DEFAULT", None) if _engine else None
)
CHECK_LABELS: Optional[Any] = (
    getattr(_engine, "CHECK_LABELS", None) if _engine else None
)


def compute_scores(
    sectors=None,
    period: str = "1y",
    interval: str = "1d",
    ttl: int = 300,
    *,
    demo: bool = False,
    json_path: str | None = None,
    seed: int = 42,
    ttl_sec: int = 0,
    download_fn=None,
):
    """
    Public API wrapper.

    Priority:
      1) demo -> engine.build_demo_dataset(...)
      2) json_path -> engine.load_json_dataset(...)
      3) live -> engine.compute_scores(...), passing through download_fn/ttl_sec when supported
         (fallback to engine.load_live_dataset(...) if present for older engines)
    """
    if _engine is None:
        raise ImportError("market_health.engine could not be imported")

    # Determine sectors (fallback to engine default if available)
    if sectors is None:
        sectors = getattr(_engine, "SECTORS_DEFAULT", None)
    if sectors is None:
        raise ValueError(
            "No sectors provided and SECTORS_DEFAULT not found in engine.py"
        )

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

    # Prefer engine.compute_scores (current implementation)
    fn = getattr(_engine, "compute_scores", None)
    if callable(fn):
        import inspect

        sig = inspect.signature(fn)
        cand = dict(
            sectors=sectors,
            period=period,
            interval=interval,
            ttl=ttl,
            ttl_sec=ttl_sec,
            download_fn=download_fn,
        )
        kwargs = {k: v for k, v in cand.items() if k in sig.parameters}
        return fn(**kwargs)

    # Fallback for older engines
    fn = getattr(_engine, "load_live_dataset", None)
    if fn is None:
        raise NotImplementedError(
            "engine.compute_scores(...) and engine.load_live_dataset(...) are both missing"
        )
    import inspect

    sig = inspect.signature(fn)
    cand = dict(sectors=sectors, period=period, interval=interval, ttl=ttl)
    kwargs = {k: v for k, v in cand.items() if k in sig.parameters}
    return fn(**kwargs)


# Version: safe at runtime and in editable installs
try:
    from importlib.metadata import version, PackageNotFoundError
except Exception:  # pragma: no cover
    from importlib_metadata import version, PackageNotFoundError  # type: ignore

try:
    __version__ = version("market-health-cli")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
