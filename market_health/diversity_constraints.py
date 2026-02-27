"""
diversity_constraints.py

Issue #111: diversity/concentration guardrails for recommendations.

- max_weight_per_symbol
- min_distinct_symbols
- HHI cap (sum(weights^2))

Pure functions; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class DiversityResult:
    ok: bool
    reasons: List[str]
    max_weight: float
    distinct: int
    hhi: float


def compute_hhi(weights: Iterable[float]) -> float:
    return float(sum(w * w for w in weights))


def normalize_weights(raw: Mapping[str, float]) -> Dict[str, float]:
    total = sum(float(v) for v in raw.values() if v is not None)
    if total <= 0:
        return {}
    out: Dict[str, float] = {}
    for k, v in raw.items():
        w = float(v)
        if w > 0:
            out[k.upper()] = w / total
    return out


def apply_swap(
    weights: Mapping[str, float],
    from_symbol: str,
    to_symbol: str,
    *,
    swap_weight: Optional[float] = None,
) -> Dict[str, float]:
    """
    Apply a swap to weights.

    If swap_weight is None:
      move ALL weight of from_symbol into to_symbol.
    Else:
      move swap_weight (clipped to available) from from_symbol -> to_symbol.
    """
    w = dict((k.upper(), float(v)) for k, v in weights.items())
    f = from_symbol.upper()
    t = to_symbol.upper()
    avail = w.get(f, 0.0)

    if swap_weight is None:
        moved = avail
    else:
        moved = min(max(float(swap_weight), 0.0), avail)

    if moved <= 0:
        return w

    w[f] = avail - moved
    w[t] = w.get(t, 0.0) + moved

    # remove near-zero dust
    if w.get(f, 0.0) <= 1e-12:
        w.pop(f, None)
    return w


def check_diversity(
    weights: Mapping[str, float],
    *,
    max_weight_per_symbol: float = 0.25,
    min_distinct_symbols: int = 4,
    hhi_cap: float = 0.20,
) -> DiversityResult:
    """
    weights are assumed normalized (sum=1). If not, we normalize.
    """
    w = normalize_weights(weights)
    if not w:
        return DiversityResult(
            ok=False, reasons=["empty_weights"], max_weight=0.0, distinct=0, hhi=0.0
        )

    vals = list(w.values())
    mx = max(vals) if vals else 0.0
    distinct = sum(1 for v in vals if v > 0)
    hhi = compute_hhi(vals)

    reasons: List[str] = []
    if mx > max_weight_per_symbol:
        reasons.append(f"max_weight_exceeded:{mx:.4f}>{max_weight_per_symbol:.4f}")
    if distinct < min_distinct_symbols:
        reasons.append(f"min_distinct_violated:{distinct}<{min_distinct_symbols}")
    if hhi > hhi_cap:
        reasons.append(f"hhi_exceeded:{hhi:.4f}>{hhi_cap:.4f}")

    return DiversityResult(
        ok=(len(reasons) == 0),
        reasons=reasons,
        max_weight=mx,
        distinct=distinct,
        hhi=hhi,
    )
