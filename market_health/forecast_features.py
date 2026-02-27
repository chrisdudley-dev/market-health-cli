"""
forecast_features.py

Shared, deterministic feature computations for forecast scoring.

Design goals
- No side effects (no file/network I/O).
- Works with plain Python lists (and also with pandas Series via sequence protocol).
- Predictable results with explicit handling of insufficient history.

Conventions
- Series are chronological (oldest -> newest).
- Windows are trading days (bars).
- Rolling outputs align to input length; values are None until enough history exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Dict, List, Optional, Sequence, Union

Number = Union[int, float]


def _as_float_list(x: Sequence[Number]) -> List[float]:
    return [float(v) for v in x]


def _require_same_length(*series: Sequence[Number]) -> int:
    if not series:
        raise ValueError("No series provided.")
    n = len(series[0])
    for s in series[1:]:
        if len(s) != n:
            raise ValueError("All series must have the same length.")
    return n


def _none_list(n: int) -> List[Optional[float]]:
    return [None] * n


def pct_change(close: Sequence[Number]) -> List[Optional[float]]:
    """Percent change close[t]/close[t-1]-1."""
    c = _as_float_list(close)
    n = len(c)
    out: List[Optional[float]] = [None] * n
    for i in range(1, n):
        prev = c[i - 1]
        out[i] = None if prev == 0 else (c[i] / prev) - 1.0
    return out


def sma(values: Sequence[Number], window: int) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    v = _as_float_list(values)
    n = len(v)
    out = _none_list(n)
    s = 0.0
    for i in range(n):
        s += v[i]
        if i >= window:
            s -= v[i - window]
        if i >= window - 1:
            out[i] = s / window
    return out


def ema(values: Sequence[Number], window: int) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    v = _as_float_list(values)
    n = len(v)
    out = _none_list(n)
    alpha = 2.0 / (window + 1.0)
    e = v[0] if n else 0.0
    for i in range(n):
        e = alpha * v[i] + (1.0 - alpha) * e
        if i >= window - 1:
            out[i] = e
    return out


def rolling_min(values: Sequence[Number], window: int) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    v = _as_float_list(values)
    n = len(v)
    out = _none_list(n)
    for i in range(n):
        if i < window - 1:
            continue
        out[i] = min(v[i - window + 1 : i + 1])
    return out


def rolling_max(values: Sequence[Number], window: int) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    v = _as_float_list(values)
    n = len(v)
    out = _none_list(n)
    for i in range(n):
        if i < window - 1:
            continue
        out[i] = max(v[i - window + 1 : i + 1])
    return out


def rolling_std(
    returns: Sequence[Optional[Number]], window: int
) -> List[Optional[float]]:
    if window <= 1:
        raise ValueError("window must be >= 2")
    r = [None if v is None else float(v) for v in returns]
    n = len(r)
    out = _none_list(n)
    for i in range(n):
        if i < window - 1:
            continue
        w = r[i - window + 1 : i + 1]
        if any(v is None for v in w):
            continue
        m = sum(w) / window  # type: ignore[arg-type]
        var = sum((v - m) ** 2 for v in w) / (window - 1)  # type: ignore[arg-type]
        out[i] = sqrt(var)
    return out


def zscore(values: Sequence[Number], window: int) -> List[Optional[float]]:
    if window <= 1:
        raise ValueError("window must be >= 2")
    v = _as_float_list(values)
    n = len(v)
    out = _none_list(n)
    for i in range(n):
        if i < window - 1:
            continue
        w = v[i - window + 1 : i + 1]
        m = sum(w) / window
        var = sum((x - m) ** 2 for x in w) / (window - 1)
        sd = sqrt(var)
        out[i] = 0.0 if sd == 0 else (v[i] - m) / sd
    return out


def rolling_percentile_rank(
    values: Sequence[Number], window: int
) -> List[Optional[float]]:
    if window <= 1:
        raise ValueError("window must be >= 2")
    v = _as_float_list(values)
    n = len(v)
    out = _none_list(n)
    for i in range(n):
        if i < window - 1:
            continue
        w = v[i - window + 1 : i + 1]
        x = w[-1]
        less = sum(1 for y in w if y < x)
        equal = sum(1 for y in w if y == x)
        out[i] = (less + 0.5 * equal) / window
    return out


def linear_regression_slope(
    values: Sequence[Number], window: int
) -> List[Optional[float]]:
    if window <= 1:
        raise ValueError("window must be >= 2")
    v = _as_float_list(values)
    n = len(v)
    out = _none_list(n)
    x_mean = (window - 1) / 2.0
    sxx = sum((i - x_mean) ** 2 for i in range(window))
    if sxx == 0:
        return out
    for idx in range(n):
        if idx < window - 1:
            continue
        y = v[idx - window + 1 : idx + 1]
        y_mean = sum(y) / window
        sxy = sum((i - x_mean) * (y[i] - y_mean) for i in range(window))
        out[idx] = sxy / sxx
    return out


def normalized_slope(
    values: Sequence[Number], window: int, eps: float = 1e-12
) -> List[Optional[float]]:
    v = _as_float_list(values)
    sl = linear_regression_slope(v, window)
    denom = sma([abs(x) for x in v], window)
    out = _none_list(len(v))
    for i in range(len(v)):
        if sl[i] is None or denom[i] is None:
            continue
        d = denom[i] if denom[i] > eps else eps
        out[i] = sl[i] / d
    return out


def true_range(
    high: Sequence[Number], low: Sequence[Number], close: Sequence[Number]
) -> List[Optional[float]]:
    _require_same_length(high, low, close)
    h = _as_float_list(high)
    lo = _as_float_list(low)
    c = _as_float_list(close)
    n = len(c)
    out = _none_list(n)
    for i in range(1, n):
        out[i] = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
    return out


def atr(
    high: Sequence[Number], low: Sequence[Number], close: Sequence[Number], window: int
) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    tr = true_range(high, low, close)
    n = len(tr)
    out = _none_list(n)
    for i in range(n):
        if i < window:
            continue
        w = tr[i - window + 1 : i + 1]
        if any(v is None for v in w):
            continue
        out[i] = sum(w) / window  # type: ignore[arg-type]
    return out


def atr_percent(
    high: Sequence[Number], low: Sequence[Number], close: Sequence[Number], window: int
) -> List[Optional[float]]:
    a = atr(high, low, close, window)
    c = _as_float_list(close)
    out = _none_list(len(c))
    for i in range(len(c)):
        if a[i] is None:
            continue
        out[i] = None if c[i] == 0 else (a[i] / c[i]) * 100.0
    return out


def bollinger_bands(
    close: Sequence[Number], window: int = 20, k: float = 2.0
) -> Dict[str, List[Optional[float]]]:
    c = _as_float_list(close)
    mid = sma(c, window)
    std = _none_list(len(c))
    for i in range(len(c)):
        if i < window - 1:
            continue
        w = c[i - window + 1 : i + 1]
        m = sum(w) / window
        var = sum((x - m) ** 2 for x in w) / (window - 1)
        std[i] = sqrt(var)

    upper = _none_list(len(c))
    lower = _none_list(len(c))
    width_pct = _none_list(len(c))
    for i in range(len(c)):
        if mid[i] is None or std[i] is None:
            continue
        upper[i] = mid[i] + k * std[i]
        lower[i] = mid[i] - k * std[i]
        width_pct[i] = None if mid[i] == 0 else ((upper[i] - lower[i]) / mid[i]) * 100.0  # type: ignore[operator]
    return {"mid": mid, "upper": upper, "lower": lower, "width_pct": width_pct}


def up_down_volume_ratio(
    close: Sequence[Number], volume: Sequence[Number], window: int = 20
) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    _require_same_length(close, volume)
    c = _as_float_list(close)
    vol = _as_float_list(volume)
    n = len(c)
    out = _none_list(n)
    up_flags = [0.0] * n
    dn_flags = [0.0] * n
    for i in range(1, n):
        if c[i] > c[i - 1]:
            up_flags[i] = vol[i]
        elif c[i] < c[i - 1]:
            dn_flags[i] = vol[i]
    for i in range(n):
        if i < window - 1:
            continue
        up = sum(up_flags[i - window + 1 : i + 1])
        dn = sum(dn_flags[i - window + 1 : i + 1])
        out[i] = None if dn == 0 else up / dn
    return out


def close_location_value(
    high: Sequence[Number], low: Sequence[Number], close: Sequence[Number]
) -> List[Optional[float]]:
    _require_same_length(high, low, close)
    h = _as_float_list(high)
    lo = _as_float_list(low)
    c = _as_float_list(close)
    n = len(c)
    out = _none_list(n)
    for i in range(n):
        rng = h[i] - lo[i]
        out[i] = None if rng == 0 else (((c[i] - lo[i]) - (h[i] - c[i])) / rng)
    return out


def rs_ratio(
    asset_close: Sequence[Number], benchmark_close: Sequence[Number]
) -> List[Optional[float]]:
    _require_same_length(asset_close, benchmark_close)
    a = _as_float_list(asset_close)
    b = _as_float_list(benchmark_close)
    out = _none_list(len(a))
    for i in range(len(a)):
        out[i] = None if b[i] == 0 else a[i] / b[i]
    return out


def rolling_correlation(
    x: Sequence[Optional[Number]], y: Sequence[Optional[Number]], window: int
) -> List[Optional[float]]:
    if window <= 1:
        raise ValueError("window must be >= 2")
    _require_same_length(x, y)
    xx = [None if v is None else float(v) for v in x]
    yy = [None if v is None else float(v) for v in y]
    n = len(xx)
    out = _none_list(n)
    for i in range(n):
        if i < window - 1:
            continue
        wx = xx[i - window + 1 : i + 1]
        wy = yy[i - window + 1 : i + 1]
        if any(v is None for v in wx) or any(v is None for v in wy):
            continue
        mx = sum(wx) / window  # type: ignore[arg-type]
        my = sum(wy) / window  # type: ignore[arg-type]
        sxx = sum((vx - mx) ** 2 for vx in wx)  # type: ignore[arg-type]
        syy = sum((vy - my) ** 2 for vy in wy)  # type: ignore[arg-type]
        if sxx == 0 or syy == 0:
            out[i] = 0.0
            continue
        sxy = sum((wx[j] - mx) * (wy[j] - my) for j in range(window))  # type: ignore[index]
        out[i] = sxy / sqrt(sxx * syy)
    return out


def cross_sectional_dispersion(
    returns_by_symbol: Dict[str, Sequence[Optional[Number]]], index: int
) -> Optional[float]:
    vals: List[float] = []
    for series in returns_by_symbol.values():
        if index >= len(series):
            return None
        v = series[index]
        if v is None:
            return None
        vals.append(float(v))
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    var = sum((x - m) ** 2 for x in vals) / (len(vals) - 1)
    return sqrt(var)


@dataclass(frozen=True)
class OHLCV:
    close: Sequence[Number]
    high: Optional[Sequence[Number]] = None
    low: Optional[Sequence[Number]] = None
    volume: Optional[Sequence[Number]] = None


class FeatureCache:
    """Compute-once cache (optional). Here kept minimal for future expansion."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(symbol)

    def set(self, symbol: str, data: Dict[str, Any]) -> None:
        self._cache[symbol] = data
