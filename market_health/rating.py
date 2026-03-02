# market_health/rating.py
from dataclasses import dataclass
from typing import Iterable, Tuple, List


@dataclass(frozen=True)
class Rating:
    label: str  # "Strong Buy"
    short: str  # "SB"
    band: Tuple[int, int]  # inclusive (lo, hi)


LABELS = [
    ("Strong Sell", "SS"),
    ("Sell", "S"),
    ("Hold", "H"),
    ("Buy", "B"),
    ("Strong Buy", "SB"),
]


def fixed_bounds() -> List[int]:
    # 4 cut points => 5 bands
    return [20, 40, 60, 80]


def quantile_bounds(scores: Iterable[int], qs=(10, 30, 70, 90)) -> List[int]:
    xs = sorted(int(s) for s in scores if s is not None)
    if not xs:
        return fixed_bounds()

    def pct(p):
        k = max(0, min(len(xs) - 1, round((p / 100) * (len(xs) - 1))))
        return xs[k]

    return [pct(q) for q in qs]


def choose_bounds(scores: Iterable[int], scheme="hybrid",
                  qs=(10, 30, 70, 90), guard=5) -> List[int]:
    """
    scheme="fixed"    -> fixed 20/40/60/80
    scheme="quantile" -> quantiles of today's cross-section
    scheme="hybrid"   -> quantiles but clamped within +/- guard of fixed bands
    """
    f = fixed_bounds()
    if scheme == "fixed":
        return f
    qb = quantile_bounds(scores, qs)
    if scheme == "quantile":
        return qb
    # hybrid: pull quantiles toward fixed by at most +/- guard
    return [max(fi - guard, min(fi + guard, qi)) for fi, qi in zip(f, qb)]


def label_for(score: int, bounds: List[int]) -> Rating:
    c1, c2, c3, c4 = bounds
    if score < c1:
        i = 0
    elif score < c2:
        i = 1
    elif score < c3:
        i = 2
    elif score < c4:
        i = 3
    else:
        i = 4
    lo = [0, c1, c2, c3, c4][i]
    hi = [c1 - 1, c2 - 1, c3 - 1, c4 - 1, 100][i]
    lbl, short = LABELS[i]
    return Rating(lbl, short, (lo, hi))
