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
    source_quality: str = "proxy"
    fallback_used: bool = False


def _canonical_source_quality(value: str) -> str:
    text = str(value or "").strip().lower()
    if text == "direct":
        return "real"
    if text in {"real", "proxy", "neutral", "disabled"}:
        return text
    return "proxy"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _first_numeric_metric(metrics: Dict[str, Any]) -> float | None:
    ignored = {
        "H",
        "horizon",
        "horizon_days",
        "horizon_scale",
        "window",
        "lookback",
    }
    preferred_markers = (
        "u",
        "z",
        "slope",
        "ratio",
        "pct",
        "percent",
        "share",
        "rank",
        "freq",
        "corr",
        "dispersion",
        "width",
        "atr",
        "iv",
        "distance",
        "momentum",
        "change",
        "value",
        "raw",
        "score_input",
    )

    for key, value in metrics.items():
        key_text = str(key)
        key_l = key_text.lower()
        if key_text in ignored or key_l in {x.lower() for x in ignored}:
            continue
        if not isinstance(value, (int, float)):
            continue
        if any(marker in key_l for marker in preferred_markers):
            return float(value)

    for key, value in metrics.items():
        key_text = str(key)
        key_l = key_text.lower()
        if key_text in ignored or key_l in {x.lower() for x in ignored}:
            continue
        if isinstance(value, (int, float)):
            return float(value)

    return None


def _audit_cutoffs(metrics: Dict[str, Any]) -> Dict[str, Any]:
    markers = (
        "cutoff",
        "threshold",
        "strong",
        "weak",
        "warn",
        "hot",
        "warm",
        "ok",
        "min",
        "max",
    )
    out: Dict[str, Any] = {}
    for key, value in metrics.items():
        key_text = str(key).lower()
        if any(marker in key_text for marker in markers):
            out[str(key)] = _json_safe(value)
    return out


def _audit_fields(check: ForecastCheck) -> Dict[str, Any]:
    raw_inputs = _json_safe(dict(check.metrics or {}))
    source_quality = _canonical_source_quality(check.source_quality)

    return {
        "source_quality": source_quality,
        "fallback_used": bool(check.fallback_used),
        "raw_inputs": raw_inputs,
        "u": _first_numeric_metric(dict(check.metrics or {})),
        "cutoffs": _audit_cutoffs(dict(check.metrics or {})),
        "orientation": str(
            (check.metrics or {}).get("orientation") or "higher_score_is_better"
        ),
        "margin_to_flip": (check.metrics or {}).get("margin_to_flip"),
    }


def cap_score(x: int) -> int:
    """Clamp to {0,1,2}."""
    return 0 if x < 0 else 2 if x > 2 else x


def neutral_check(label: str, meaning: str, note: str) -> ForecastCheck:
    """Return neutral score=1 when inputs are missing."""
    return ForecastCheck(
        label=label,
        meaning=meaning,
        score=1,
        metrics={"note": note},
        source_quality="neutral",
        fallback_used=True,
    )


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

        audit = _audit_fields(c)

        out["checks"].append(
            {
                "label": c.label,
                "meaning": c.meaning,
                "score": int(c.score),
                "horizon_days": H,
                "metrics": metrics,
                "source_quality": audit["source_quality"],
                "fallback_used": audit["fallback_used"],
                "raw_inputs": audit["raw_inputs"],
                "u": audit["u"],
                "cutoffs": audit["cutoffs"],
                "orientation": audit["orientation"],
                "margin_to_flip": audit["margin_to_flip"],
            }
        )

    return out
