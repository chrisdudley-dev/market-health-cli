from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

CALIBRATION_V1_SCHEMA = "calibration.v1"

# Keep these aligned with the current CLI defaults.
DEFAULT_THRESHOLDS: Dict[str, float] = {
    # Used by forecast-mode recommendation selection.
    "min_improvement_threshold": 0.12,
    # Used by disagreement veto logic.
    "disagreement_veto_edge": 0.08,
}

DEFAULT_CONSTRAINTS: Dict[str, Any] = {
    # Portfolio constraints used in forecast-mode recommendations.
    "max_weight_per_symbol": 0.25,
    "min_distinct_symbols": 5,
    "hhi_cap": 0.25,
}


def build_calibration_v1(
    *,
    asof_date: dt.date,
    thresholds: Optional[Dict[str, Any]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    th = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    cs = dict(DEFAULT_CONSTRAINTS)
    if constraints:
        cs.update(constraints)

    doc: Dict[str, Any] = {
        "schema": CALIBRATION_V1_SCHEMA,
        "asof_date": asof_date.isoformat(),
        "thresholds": th,
        "constraints": cs,
        "notes": notes or "Defaults for forecast-mode recommendation calibration.",
    }
    return doc


def validate_calibration_v1(doc: Any) -> List[str]:
    errors: List[str] = []

    def err(msg: str) -> None:
        errors.append(msg)

    if not isinstance(doc, dict):
        return ["doc must be a dict"]

    if doc.get("schema") != CALIBRATION_V1_SCHEMA:
        err(f'schema must be "{CALIBRATION_V1_SCHEMA}"')

    asof = doc.get("asof_date")
    if not isinstance(asof, str):
        err("asof_date must be ISO date string")
    else:
        try:
            dt.date.fromisoformat(asof)
        except Exception:
            err("asof_date must be YYYY-MM-DD")

    th = doc.get("thresholds")
    if not isinstance(th, dict):
        err("thresholds must be a dict")
    else:
        for k in ("min_improvement_threshold", "disagreement_veto_edge"):
            v = th.get(k)
            if not isinstance(v, (int, float)):
                err(f"thresholds.{k} must be number")

    cs = doc.get("constraints")
    if not isinstance(cs, dict):
        err("constraints must be a dict")
    else:
        if not isinstance(cs.get("max_weight_per_symbol"), (int, float)):
            err("constraints.max_weight_per_symbol must be number")
        if not isinstance(cs.get("min_distinct_symbols"), int):
            err("constraints.min_distinct_symbols must be int")
        if not isinstance(cs.get("hhi_cap"), (int, float)):
            err("constraints.hhi_cap must be number")

    notes = doc.get("notes")
    if notes is not None and not isinstance(notes, str):
        err("notes must be string if present")

    return errors
