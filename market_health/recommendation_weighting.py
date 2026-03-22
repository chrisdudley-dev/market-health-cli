from __future__ import annotations

from typing import Any, Dict, List, Mapping

DEFAULT_UTILITY_WEIGHTS: Dict[str, float] = {
    "c": 0.50,
    "h1": 0.25,
    "h5": 0.25,
}

DEFAULT_WEIGHTING_PROFILE: Dict[str, Any] = {
    "base_utility_weights": dict(DEFAULT_UTILITY_WEIGHTS),
    "regime_overrides": {
        "neutral": {},
        "risk_on": {"c": 0.40, "h1": 0.25, "h5": 0.35},
        "risk_off": {"c": 0.60, "h1": 0.20, "h5": 0.20},
        "sideways": {"c": 0.55, "h1": 0.25, "h5": 0.20},
    },
    "symbol_family_overrides": {
        "generic_equity": {},
        "sector_etf": {"c": 0.45, "h1": 0.25, "h5": 0.30},
        "broad_index": {"c": 0.40, "h1": 0.25, "h5": 0.35},
        "metals": {"c": 0.35, "h1": 0.20, "h5": 0.45},
        "rates": {"c": 0.55, "h1": 0.20, "h5": 0.25},
    },
}


def _f(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def normalize_utility_weights(raw: Mapping[str, Any] | None) -> Dict[str, float]:
    out = dict(DEFAULT_UTILITY_WEIGHTS)
    if isinstance(raw, Mapping):
        for key in ("c", "h1", "h5"):
            val = _f(raw.get(key))
            if val is not None and val >= 0:
                out[key] = val

    total = sum(out.values())
    if total <= 0:
        return dict(DEFAULT_UTILITY_WEIGHTS)

    return {k: float(v) / total for k, v in out.items()}


def resolve_regime_key(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "neutral"

    x = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if x in {"risk_on", "bullish"}:
        return "risk_on"
    if x in {"risk_off", "bearish"}:
        return "risk_off"
    if x in {"sideways", "rangebound", "range_bound"}:
        return "sideways"
    return "neutral"


def infer_symbol_family(symbol: str) -> str:
    sym = str(symbol or "").upper()

    if sym.startswith("XL"):
        return "sector_etf"
    if sym in {"SPY", "QQQ", "DIA", "IWM", "EWJ", "VGK", "EEM", "FXI"}:
        return "broad_index"
    if sym in {"GLD", "IAU", "SLV", "PPLT", "PALL", "GDX", "GDXJ"}:
        return "metals"
    if sym in {"TLT", "IEF", "SHY", "LQD", "HYG", "BND"}:
        return "rates"
    return "generic_equity"


def resolve_utility_weights(
    *,
    base_weights: Mapping[str, Any] | None,
    weighting_profile: Mapping[str, Any] | None,
    regime_key: Any,
    symbol_family: Any,
) -> Dict[str, Any]:
    base = normalize_utility_weights(base_weights)

    profile = (
        weighting_profile
        if isinstance(weighting_profile, Mapping)
        else DEFAULT_WEIGHTING_PROFILE
    )

    regime = resolve_regime_key(regime_key)
    family = (
        str(symbol_family).strip().lower()
        if isinstance(symbol_family, str) and str(symbol_family).strip()
        else "generic_equity"
    )

    regime_overrides = profile.get("regime_overrides")
    family_overrides = profile.get("symbol_family_overrides")

    weights = dict(base)

    if isinstance(regime_overrides, Mapping):
        regime_patch = regime_overrides.get(regime)
        if isinstance(regime_patch, Mapping):
            weights.update(
                {
                    k: float(v)
                    for k, v in regime_patch.items()
                    if k in {"c", "h1", "h5"} and isinstance(v, (int, float))
                }
            )

    if isinstance(family_overrides, Mapping):
        family_patch = family_overrides.get(family)
        if isinstance(family_patch, Mapping):
            weights.update(
                {
                    k: float(v)
                    for k, v in family_patch.items()
                    if k in {"c", "h1", "h5"} and isinstance(v, (int, float))
                }
            )

    return {
        "regime": regime,
        "symbol_family": family,
        "weights": normalize_utility_weights(weights),
    }


def validate_weighting_profile(profile: Any) -> List[str]:
    errors: List[str] = []

    if not isinstance(profile, Mapping):
        return ["weighting must be a dict"]

    base = profile.get("base_utility_weights")
    if not isinstance(base, Mapping):
        errors.append("weighting.base_utility_weights must be a dict")
    else:
        for key in ("c", "h1", "h5"):
            if not isinstance(base.get(key), (int, float)):
                errors.append(f"weighting.base_utility_weights.{key} must be number")

    for section_name in ("regime_overrides", "symbol_family_overrides"):
        section = profile.get(section_name)
        if not isinstance(section, Mapping):
            errors.append(f"weighting.{section_name} must be a dict")
            continue
        for scope_key, scope_val in section.items():
            if not isinstance(scope_val, Mapping):
                errors.append(f"weighting.{section_name}.{scope_key} must be a dict")
                continue
            for key, val in scope_val.items():
                if key not in {"c", "h1", "h5"}:
                    errors.append(
                        f"weighting.{section_name}.{scope_key}.{key} is not supported"
                    )
                    continue
                if not isinstance(val, (int, float)):
                    errors.append(
                        f"weighting.{section_name}.{scope_key}.{key} must be number"
                    )

    return errors
