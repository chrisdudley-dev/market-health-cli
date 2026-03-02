"""
Market Health public API.

This module provides a stable surface for callers/tests while allowing the
engine implementation to evolve.

Public:
- compute_scores(...)
- SECTORS_DEFAULT (if available in engine)
- CHECK_LABELS    (if available in engine)
- __version__
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from importlib.metadata import PackageNotFoundError, version
except Exception:  # pragma: no cover
    PackageNotFoundError = Exception  # type: ignore
    version = None  # type: ignore

try:
    __version__ = version("market-health-cli") if version else "0+unknown"
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0+unknown"


try:
    from . import engine as _engine  # type: ignore
except ImportError:  # pragma: no cover
    _engine = None  # type: ignore


SECTORS_DEFAULT: Optional[Any] = getattr(_engine, "SECTORS_DEFAULT", None) if _engine else None
CHECK_LABELS: Optional[Any] = getattr(_engine, "CHECK_LABELS", None) if _engine else None


def compute_scores(
    sectors=None,
    period: str = "1y",
    interval: str = "1d",
    ttl_sec: int = 300,
    download_fn=None,
    # Back-compat: some callers still pass ttl=
    ttl: Optional[int] = None,
    **_ignored,
):
    """
    Compute sector scores via market_health.engine, with a stable signature.

    Supports dependency injection for offline tests:
      - ttl_sec=0
      - download_fn=fake_download
    """
    if _engine is None:
        raise ImportError("market_health.engine could not be imported")

    # Back-compat: if caller uses ttl=, map it to ttl_sec (unless ttl_sec explicitly set).
    if ttl is not None and ttl_sec == 300:
        ttl_sec = int(ttl)

    if sectors is None:
        sectors = getattr(_engine, "SECTORS_DEFAULT", None)
    if sectors is None:
        raise ValueError("No sectors provided and SECTORS_DEFAULT not found in engine.py")

    # Prefer engine.compute_scores if present (current implementation).
    fn = getattr(_engine, "compute_scores", None)
    if callable(fn):
        import inspect

        sig = inspect.signature(fn)
        cand = {
            "sectors": sectors,
            "period": period,
            "interval": interval,
            "ttl_sec": ttl_sec,
            "download_fn": download_fn,
        }
        kwargs = {k: v for k, v in cand.items() if k in sig.parameters}
        return fn(**kwargs)

    # Fallback for older engines
    fn = getattr(_engine, "load_live_dataset", None)
    if callable(fn):
        import inspect

        sig = inspect.signature(fn)
        cand = {
            "sectors": sectors,
            "period": period,
            "interval": interval,
            "ttl": ttl_sec,  # old API expected ttl
        }
        kwargs = {k: v for k, v in cand.items() if k in sig.parameters}
        return fn(**kwargs)

    raise NotImplementedError("engine.compute_scores(...) is missing")


__all__ = ["compute_scores", "SECTORS_DEFAULT", "CHECK_LABELS", "__version__"]
