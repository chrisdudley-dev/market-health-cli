"""
forecast_types.py

Shared types and small helpers for forecast-mode scoring.
No math and no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class ForecastCheck:
    """
    A single forecast-mode check.

    score: 0/1/2
    metrics: debug payload to explain how the score was produced
    """
    label: str
    meaning: str
    score: int
    metrics: Dict[str, Any]


def cap_score(x: int) -> int:
    """Clamp to {0,1,2}."""
    return 0 if x < 0 else 2 if x > 2 else x


def neutral_check(label: str, meaning: str, note: str) -> ForecastCheck:
    """Return neutral score=1 when inputs are missing."""
    return ForecastCheck(label=label, meaning=meaning, score=1, metrics={"note": note})


def sum_points(checks: List[ForecastCheck]) -> Tuple[int, int]:
    """Return (points, max_points) for a list of 0/1/2 checks."""
    pts = sum(int(c.score) for c in checks)
    mx = 2 * len(checks)
    return pts, mx


def category_dict(checks: List[ForecastCheck]) -> Dict[str, Any]:
    """Serialize a category (A–E) to a JSON-friendly dict."""
    pts, mx = sum_points(checks)
    return {
        "checks": [
            {"label": c.label, "meaning": c.meaning, "score": int(c.score), "metrics": c.metrics}
            for c in checks
        ],
        "points": pts,
        "max_points": mx,
        "pct": (pts / mx) if mx else 0.0,
    }
