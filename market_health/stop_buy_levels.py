from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

CandidateKind = Literal["floor", "ceiling"]


@dataclass(frozen=True)
class StopBuyCandidate:
    level: float
    kind: CandidateKind
    source: str
    weight: float
    recency: int | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "level": round(float(self.level), 6),
            "kind": self.kind,
            "source": self.source,
            "weight": round(float(self.weight), 6),
        }
        if self.recency is not None:
            out["recency"] = int(self.recency)
        if self.detail:
            out["detail"] = self.detail
        return out


def _col(df: pd.DataFrame, name: str) -> pd.Series | None:
    if name in df:
        return pd.to_numeric(df[name], errors="coerce")

    lowered = {str(c).lower(): c for c in df.columns}
    key = name.lower()
    if key in lowered:
        return pd.to_numeric(df[lowered[key]], errors="coerce")

    return None


def _last(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[-1])


def _append_candidate(
    out: list[StopBuyCandidate],
    *,
    level: float | None,
    kind: CandidateKind,
    source: str,
    weight: float,
    current_price: float,
    recency: int | None = None,
    detail: str | None = None,
) -> None:
    if level is None:
        return

    level = float(level)

    if kind == "floor" and level >= current_price:
        return
    if kind == "ceiling" and level <= current_price:
        return

    out.append(
        StopBuyCandidate(
            level=level,
            kind=kind,
            source=source,
            weight=float(weight),
            recency=recency,
            detail=detail,
        )
    )


def _add_rolling_extremes(
    out: list[StopBuyCandidate],
    *,
    high: pd.Series | None,
    low: pd.Series | None,
    current_price: float,
    windows: tuple[int, ...] = (10, 20, 50),
) -> None:
    for window in windows:
        if low is not None and len(low.dropna()) >= 2:
            value = _last(low.rolling(window, min_periods=2).min())
            _append_candidate(
                out,
                level=value,
                kind="floor",
                source=f"rolling_low_{window}d",
                weight=0.85,
                current_price=current_price,
                detail=f"{window}-day rolling low",
            )

        if high is not None and len(high.dropna()) >= 2:
            value = _last(high.rolling(window, min_periods=2).max())
            _append_candidate(
                out,
                level=value,
                kind="ceiling",
                source=f"rolling_high_{window}d",
                weight=0.85,
                current_price=current_price,
                detail=f"{window}-day rolling high",
            )


def _add_moving_averages(
    out: list[StopBuyCandidate],
    *,
    close: pd.Series,
    current_price: float,
) -> None:
    for span in (8, 21):
        value = _last(close.ewm(span=span, adjust=False).mean())
        if value is None:
            continue
        kind: CandidateKind = "floor" if value < current_price else "ceiling"
        _append_candidate(
            out,
            level=value,
            kind=kind,
            source=f"ema_{span}",
            weight=0.70,
            current_price=current_price,
            detail=f"EMA {span}",
        )

    for window in (50, 200):
        if len(close.dropna()) < 2:
            continue
        value = _last(close.rolling(window, min_periods=2).mean())
        if value is None:
            continue
        kind = "floor" if value < current_price else "ceiling"
        _append_candidate(
            out,
            level=value,
            kind=kind,
            source=f"sma_{window}",
            weight=0.65,
            current_price=current_price,
            detail=f"SMA {window}",
        )


def _add_rolling_vwap(
    out: list[StopBuyCandidate],
    *,
    close: pd.Series,
    volume: pd.Series | None,
    current_price: float,
    windows: tuple[int, ...] = (20, 50),
) -> None:
    if volume is None:
        return

    for window in windows:
        valid = pd.DataFrame({"close": close, "volume": volume}).dropna()
        if len(valid) < 2:
            continue

        numerator = (
            (valid["close"] * valid["volume"]).rolling(window, min_periods=2).sum()
        )
        denominator = valid["volume"].rolling(window, min_periods=2).sum()
        vwap = numerator / denominator.replace(0, pd.NA)
        value = _last(vwap)

        if value is None:
            continue

        kind: CandidateKind = "floor" if value < current_price else "ceiling"
        _append_candidate(
            out,
            level=value,
            kind=kind,
            source=f"rolling_vwap_{window}d",
            weight=0.75,
            current_price=current_price,
            detail=f"{window}-day rolling VWAP",
        )


def _add_swing_points(
    out: list[StopBuyCandidate],
    *,
    high: pd.Series | None,
    low: pd.Series | None,
    current_price: float,
    lookback: int,
) -> None:
    if high is not None:
        h = high.dropna().tail(lookback)
        values = h.to_list()
        indexes = list(h.index)
        n = len(values)

        for i in range(1, n - 1):
            if values[i] > values[i - 1] and values[i] >= values[i + 1]:
                recency = n - 1 - i
                _append_candidate(
                    out,
                    level=values[i],
                    kind="ceiling",
                    source="swing_high",
                    weight=1.00,
                    current_price=current_price,
                    recency=recency,
                    detail=f"swing high at {indexes[i]}",
                )

    if low is not None:
        lows = low.dropna().tail(lookback)
        values = lows.to_list()
        indexes = list(lows.index)
        n = len(values)

        for i in range(1, n - 1):
            if values[i] < values[i - 1] and values[i] <= values[i + 1]:
                recency = n - 1 - i
                _append_candidate(
                    out,
                    level=values[i],
                    kind="floor",
                    source="swing_low",
                    weight=1.00,
                    current_price=current_price,
                    recency=recency,
                    detail=f"swing low at {indexes[i]}",
                )


def _add_gap_edges(
    out: list[StopBuyCandidate],
    *,
    high: pd.Series | None,
    low: pd.Series | None,
    current_price: float,
    lookback: int,
) -> None:
    if high is None or low is None:
        return

    frame = pd.DataFrame({"high": high, "low": low}).dropna().tail(lookback)
    if len(frame) < 2:
        return

    rows = frame.reset_index(drop=True)

    for i in range(1, len(rows)):
        prev_high = float(rows.loc[i - 1, "high"])
        prev_low = float(rows.loc[i - 1, "low"])
        this_low = float(rows.loc[i, "low"])
        this_high = float(rows.loc[i, "high"])
        recency = len(rows) - 1 - i

        if this_low > prev_high:
            _append_candidate(
                out,
                level=prev_high,
                kind="floor",
                source="gap_up_lower_edge",
                weight=0.60,
                current_price=current_price,
                recency=recency,
                detail="prior high below gap-up window",
            )
            _append_candidate(
                out,
                level=this_low,
                kind="floor",
                source="gap_up_upper_edge",
                weight=0.60,
                current_price=current_price,
                recency=recency,
                detail="current low above gap-up window",
            )

        if this_high < prev_low:
            _append_candidate(
                out,
                level=prev_low,
                kind="ceiling",
                source="gap_down_upper_edge",
                weight=0.60,
                current_price=current_price,
                recency=recency,
                detail="prior low above gap-down window",
            )
            _append_candidate(
                out,
                level=this_high,
                kind="ceiling",
                source="gap_down_lower_edge",
                weight=0.60,
                current_price=current_price,
                recency=recency,
                detail="current high below gap-down window",
            )


def _add_volume_shelves(
    out: list[StopBuyCandidate],
    *,
    close: pd.Series,
    volume: pd.Series | None,
    current_price: float,
    lookback: int,
    bins: int = 12,
) -> None:
    if volume is None:
        return

    frame = pd.DataFrame({"close": close, "volume": volume}).dropna().tail(lookback)
    if len(frame) < 5:
        return
    if float(frame["volume"].sum()) <= 0:
        return

    price_min = float(frame["close"].min())
    price_max = float(frame["close"].max())
    if price_min == price_max:
        return

    bucket_count = min(bins, max(3, len(frame) // 3))
    frame = frame.copy()
    frame["bucket"] = pd.cut(frame["close"], bins=bucket_count, include_lowest=True)

    grouped = (
        frame.groupby("bucket", observed=True)
        .agg(volume=("volume", "sum"), level=("close", "mean"))
        .sort_values(["volume", "level"], ascending=[False, True])
        .head(5)
    )

    for rank, row in enumerate(grouped.itertuples(), start=1):
        level = float(row.level)
        weight = max(0.35, 0.70 - (rank - 1) * 0.07)
        kind: CandidateKind = "floor" if level < current_price else "ceiling"
        _append_candidate(
            out,
            level=level,
            kind=kind,
            source="volume_shelf_60d",
            weight=weight,
            current_price=current_price,
            detail="high-volume close-price bucket",
        )


def generate_stop_buy_candidates(
    df: pd.DataFrame,
    *,
    lookback: int = 60,
) -> list[dict[str, Any]]:
    """Return deterministic floor and ceiling candidates for Stop/Buy math.

    This is candidate generation only. It does not select final dashboard Stop/Buy
    levels and does not change existing dashboard behavior.
    """

    if df.empty:
        return []

    high = _col(df, "High")
    low = _col(df, "Low")
    close = _col(df, "Close")
    volume = _col(df, "Volume")

    current_price = _last(close)
    if current_price is None:
        return []

    out: list[StopBuyCandidate] = []

    _add_rolling_extremes(out, high=high, low=low, current_price=current_price)
    _add_moving_averages(out, close=close, current_price=current_price)
    _add_rolling_vwap(out, close=close, volume=volume, current_price=current_price)
    _add_swing_points(
        out,
        high=high,
        low=low,
        current_price=current_price,
        lookback=lookback,
    )
    _add_gap_edges(
        out,
        high=high,
        low=low,
        current_price=current_price,
        lookback=lookback,
    )
    _add_volume_shelves(
        out,
        close=close,
        volume=volume,
        current_price=current_price,
        lookback=lookback,
    )

    deduped: dict[tuple[str, str, float], StopBuyCandidate] = {}
    for candidate in out:
        key = (candidate.kind, candidate.source, round(candidate.level, 4))
        previous = deduped.get(key)
        if previous is None or candidate.weight > previous.weight:
            deduped[key] = candidate

    return [
        candidate.as_dict()
        for candidate in sorted(
            deduped.values(),
            key=lambda c: (
                c.kind,
                c.source,
                round(c.level, 6),
                c.recency if c.recency is not None else 999999,
            ),
        )
    ]


def _candidate_level(candidate: dict[str, Any]) -> float | None:
    try:
        return float(candidate["level"])
    except Exception:
        return None


def _candidate_weight(candidate: dict[str, Any]) -> float:
    try:
        return max(float(candidate.get("weight", 1.0)), 0.0)
    except Exception:
        return 1.0


def _candidate_recency(candidate: dict[str, Any]) -> int | None:
    try:
        value = candidate.get("recency")
        return None if value is None else int(value)
    except Exception:
        return None


def _cluster_threshold(
    *,
    reference_level: float,
    current_price: float | None,
    atr: float | None,
    max_distance_pct: float,
    max_distance_atr: float,
) -> float:
    anchors = [abs(float(reference_level))]

    if current_price is not None:
        anchors.append(abs(float(current_price)))

    pct_threshold = max(anchors) * float(max_distance_pct)

    if atr is not None and atr > 0:
        atr_threshold = float(atr) * float(max_distance_atr)
        return max(pct_threshold, atr_threshold)

    return pct_threshold


def cluster_stop_buy_candidates(
    candidates: list[dict[str, Any]],
    *,
    kind: CandidateKind | None = None,
    current_price: float | None = None,
    atr: float | None = None,
    max_distance_pct: float = 0.0075,
    max_distance_atr: float = 0.50,
    min_cluster_weight: float = 0.0,
    min_cluster_size: int = 1,
) -> list[dict[str, Any]]:
    """Cluster nearby Stop/Buy candidates and leave distant levels as separate outliers.

    This is clustering only. It does not select final dashboard Stop/Buy levels and
    does not change existing dashboard behavior.
    """

    normalized: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        candidate_kind = candidate.get("kind")
        if candidate_kind not in {"floor", "ceiling"}:
            continue
        if kind is not None and candidate_kind != kind:
            continue

        level = _candidate_level(candidate)
        if level is None:
            continue

        weight = _candidate_weight(candidate)

        normalized.append(
            {
                "level": float(level),
                "kind": candidate_kind,
                "source": str(candidate.get("source") or "unknown"),
                "weight": weight,
                "recency": _candidate_recency(candidate),
                "detail": candidate.get("detail"),
            }
        )

    normalized.sort(key=lambda item: (item["kind"], item["level"], item["source"]))

    clusters_raw: list[list[dict[str, Any]]] = []

    for candidate in normalized:
        if not clusters_raw:
            clusters_raw.append([candidate])
            continue

        previous_cluster = clusters_raw[-1]
        previous_kind = previous_cluster[0]["kind"]

        if candidate["kind"] != previous_kind:
            clusters_raw.append([candidate])
            continue

        total_weight = sum(_candidate_weight(item) for item in previous_cluster)
        if total_weight > 0:
            reference_level = (
                sum(
                    float(item["level"]) * _candidate_weight(item)
                    for item in previous_cluster
                )
                / total_weight
            )
        else:
            reference_level = float(previous_cluster[-1]["level"])

        threshold = _cluster_threshold(
            reference_level=reference_level,
            current_price=current_price,
            atr=atr,
            max_distance_pct=max_distance_pct,
            max_distance_atr=max_distance_atr,
        )

        if abs(float(candidate["level"]) - reference_level) <= threshold:
            previous_cluster.append(candidate)
        else:
            clusters_raw.append([candidate])

    clusters: list[dict[str, Any]] = []

    for cluster in clusters_raw:
        total_weight = sum(_candidate_weight(item) for item in cluster)
        if len(cluster) < int(min_cluster_size):
            continue
        if total_weight < float(min_cluster_weight):
            continue

        levels = [float(item["level"]) for item in cluster]
        if total_weight > 0:
            center = (
                sum(float(item["level"]) * _candidate_weight(item) for item in cluster)
                / total_weight
            )
        else:
            center = sum(levels) / len(levels)

        recencies = [
            int(item["recency"]) for item in cluster if item.get("recency") is not None
        ]
        sources = sorted({str(item["source"]) for item in cluster})

        cluster_kind = str(cluster[0]["kind"])
        strength = total_weight * (1.0 + 0.15 * max(len(sources) - 1, 0))

        clusters.append(
            {
                "kind": cluster_kind,
                "center": round(float(center), 6),
                "lower": round(float(min(levels)), 6),
                "upper": round(float(max(levels)), 6),
                "weight": round(float(total_weight), 6),
                "strength": round(float(strength), 6),
                "count": len(cluster),
                "sources": sources,
                "nearest_recency": min(recencies) if recencies else None,
                "is_outlier": len(cluster) == 1,
            }
        )

    return sorted(
        clusters,
        key=lambda item: (
            str(item["kind"]),
            -float(item["strength"]),
            -int(item["count"]),
            float(item["center"]),
        ),
    )


def strongest_stop_buy_clusters(
    candidates: list[dict[str, Any]],
    *,
    current_price: float | None = None,
    atr: float | None = None,
    max_distance_pct: float = 0.0075,
    max_distance_atr: float = 0.50,
    min_cluster_weight: float = 0.0,
    min_cluster_size: int = 1,
) -> dict[str, dict[str, Any] | None]:
    """Return the strongest floor and ceiling clusters from candidate levels."""

    clusters = cluster_stop_buy_candidates(
        candidates,
        current_price=current_price,
        atr=atr,
        max_distance_pct=max_distance_pct,
        max_distance_atr=max_distance_atr,
        min_cluster_weight=min_cluster_weight,
        min_cluster_size=min_cluster_size,
    )

    floors = [cluster for cluster in clusters if cluster["kind"] == "floor"]
    ceilings = [cluster for cluster in clusters if cluster["kind"] == "ceiling"]

    return {
        "floor": floors[0] if floors else None,
        "ceiling": ceilings[0] if ceilings else None,
    }
