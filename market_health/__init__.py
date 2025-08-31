"""
Market Health engine package.
Exports the public API so callers can do: `from market_health import compute_scores`.
"""

from .engine import compute_scores, CHECK_LABELS

__all__ = ["compute_scores", "CHECK_LABELS"]
__version__ = "0.1.0"
