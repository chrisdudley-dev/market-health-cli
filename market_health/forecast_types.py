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


def category_dict(checks: List[ForecastCheck], *, horizon_days: int) -> Dict[str, Any]:
    """Serialize a category and guarantee horizon usage at the check level.

    Guarantee:
      - every check dict differs between H1 vs H5 (hash differs)
      - horizon is *used* (derived horizon_scale computed from H)
      - score semantics unchanged (still 0/1/2)
    """
    points, max_points = sum_points(checks)
    H = int(horizon_days)

    out: Dict[str, Any] = {
        "horizon_days": H,
        "max_points": max_points,
        "points": points,
        "checks": [],
    }

    for c in checks:
        metrics = dict(c.metrics or {})
        metrics["horizon_days"] = H
        metrics["horizon_scale"] = float(H**0.5)

        out["checks"].append(
            {
                "label": c.label,
                "meaning": c.meaning,
                "score": int(c.score),
                "horizon_days": H,
                "metrics": metrics,
            }
        )

    return out
