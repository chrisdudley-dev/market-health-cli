from __future__ import annotations

from market_health.stop_buy_levels import (
    cluster_stop_buy_candidates,
    strongest_stop_buy_clusters,
)


def test_cluster_stop_buy_candidates_groups_nearby_floor_levels():
    candidates = [
        {"level": 98.00, "kind": "floor", "source": "swing_low", "weight": 1.0},
        {"level": 98.25, "kind": "floor", "source": "ema_21", "weight": 0.7},
        {"level": 98.40, "kind": "floor", "source": "rolling_low_20d", "weight": 0.85},
        {"level": 90.00, "kind": "floor", "source": "distant_low", "weight": 1.0},
    ]

    clusters = cluster_stop_buy_candidates(
        candidates,
        kind="floor",
        current_price=100.0,
        atr=2.0,
        max_distance_pct=0.005,
        max_distance_atr=0.50,
    )

    assert len(clusters) == 2

    strongest = clusters[0]
    outlier = clusters[1]

    assert strongest["kind"] == "floor"
    assert strongest["count"] == 3
    assert strongest["is_outlier"] is False
    assert strongest["lower"] == 98.0
    assert strongest["upper"] == 98.4
    assert set(strongest["sources"]) == {"ema_21", "rolling_low_20d", "swing_low"}

    assert outlier["count"] == 1
    assert outlier["is_outlier"] is True
    assert outlier["center"] == 90.0


def test_cluster_stop_buy_candidates_groups_nearby_ceiling_levels():
    candidates = [
        {"level": 105.00, "kind": "ceiling", "source": "swing_high", "weight": 1.0},
        {
            "level": 105.35,
            "kind": "ceiling",
            "source": "rolling_high_20d",
            "weight": 0.85,
        },
        {"level": 112.00, "kind": "ceiling", "source": "distant_high", "weight": 1.0},
    ]

    clusters = cluster_stop_buy_candidates(
        candidates,
        kind="ceiling",
        current_price=100.0,
        atr=2.0,
        max_distance_pct=0.005,
        max_distance_atr=0.50,
    )

    assert len(clusters) == 2

    strongest = clusters[0]

    assert strongest["kind"] == "ceiling"
    assert strongest["count"] == 2
    assert strongest["is_outlier"] is False
    assert strongest["lower"] == 105.0
    assert strongest["upper"] == 105.35
    assert set(strongest["sources"]) == {"rolling_high_20d", "swing_high"}


def test_strongest_stop_buy_clusters_returns_best_floor_and_ceiling():
    candidates = [
        {"level": 97.90, "kind": "floor", "source": "swing_low", "weight": 1.0},
        {"level": 98.10, "kind": "floor", "source": "ema_21", "weight": 0.7},
        {"level": 104.90, "kind": "ceiling", "source": "swing_high", "weight": 1.0},
        {
            "level": 105.10,
            "kind": "ceiling",
            "source": "rolling_high_20d",
            "weight": 0.85,
        },
    ]

    result = strongest_stop_buy_clusters(candidates, current_price=100.0, atr=2.0)

    assert result["floor"] is not None
    assert result["ceiling"] is not None
    assert result["floor"]["kind"] == "floor"
    assert result["ceiling"]["kind"] == "ceiling"
    assert result["floor"]["count"] == 2
    assert result["ceiling"]["count"] == 2


def test_cluster_stop_buy_candidates_filters_by_minimum_cluster_size():
    candidates = [
        {"level": 98.00, "kind": "floor", "source": "swing_low", "weight": 1.0},
        {"level": 90.00, "kind": "floor", "source": "distant_low", "weight": 1.0},
    ]

    clusters = cluster_stop_buy_candidates(
        candidates,
        kind="floor",
        current_price=100.0,
        min_cluster_size=2,
    )

    assert clusters == []


def test_cluster_stop_buy_candidates_ignores_invalid_candidates():
    candidates = [
        {"level": "not-a-number", "kind": "floor", "source": "bad", "weight": 1.0},
        {"level": 98.0, "kind": "unknown", "source": "bad", "weight": 1.0},
        {"level": 98.0, "kind": "floor", "source": "good", "weight": 1.0},
    ]

    clusters = cluster_stop_buy_candidates(candidates, current_price=100.0)

    assert len(clusters) == 1
    assert clusters[0]["sources"] == ["good"]
