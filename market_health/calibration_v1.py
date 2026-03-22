from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from market_health.recommendation_weighting import (
    DEFAULT_WEIGHTING_PROFILE,
    validate_weighting_profile,
)

CALIBRATION_V1_SCHEMA = "calibration.v1"

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "min_improvement_threshold": 0.12,
    "disagreement_veto_edge": 0.08,
}

DEFAULT_CONSTRAINTS: Dict[str, Any] = {
    "max_weight_per_symbol": 0.25,
    "min_distinct_symbols": 5,
    "hhi_cap": 0.25,
}


def _copy_weighting(weighting: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = {
        "base_utility_weights": dict(
            DEFAULT_WEIGHTING_PROFILE.get("base_utility_weights") or {}
        ),
        "regime_overrides": {
            str(k): dict(v)
            for k, v in (
                DEFAULT_WEIGHTING_PROFILE.get("regime_overrides") or {}
            ).items()
        },
        "symbol_family_overrides": {
            str(k): dict(v)
            for k, v in (
                DEFAULT_WEIGHTING_PROFILE.get("symbol_family_overrides") or {}
            ).items()
        },
    }

    if not isinstance(weighting, dict):
        return base

    for key in ("base_utility_weights", "regime_overrides", "symbol_family_overrides"):
        val = weighting.get(key)
        if isinstance(val, dict):
            if key == "base_utility_weights":
                base[key].update(val)
            else:
                for sk, sv in val.items():
                    if isinstance(sv, dict):
                        base[key][str(sk)] = dict(sv)
    return base


def build_calibration_v1(
    *,
    asof_date: dt.date,
    thresholds: Optional[Dict[str, Any]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    weighting: Optional[Dict[str, Any]] = None,
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
        "source": "calibration.v1",
        "thresholds": th,
        "constraints": cs,
        "weighting": _copy_weighting(weighting),
        "notes": notes
        or "Defaults for forecast-mode recommendation calibration, including regime and symbol-family weighting overrides.",
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
            if not isinstance(th.get(k), (int, float)):
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

    weighting_errors = validate_weighting_profile(doc.get("weighting"))
    errors.extend(weighting_errors)

    source = doc.get("source")
    if source is not None and not isinstance(source, str):
        err("source must be string if present")

    notes = doc.get("notes")
    if notes is not None and not isinstance(notes, str):
        err("notes must be string if present")

    return errors
