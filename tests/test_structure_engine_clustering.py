from math import isclose

from market_health.structure_engine import RawLevel, cluster_raw_levels_into_zones


def test_cluster_support_levels_within_zone_width() -> None:
    raw_levels = [
        RawLevel(100.0, "support", "a", "1d", "s1"),
        RawLevel(100.2, "support", "b", "1d", "s2"),
        RawLevel(102.0, "support", "c", "1d", "s3"),
    ]
    zones = cluster_raw_levels_into_zones(raw_levels, zone_width=0.5)

    assert len(zones) == 2
    first, second = zones
    assert first.kind == "support"
    assert isclose(first.lower, 100.0)
    assert isclose(first.upper, 100.2)
    assert isclose(first.center, 100.1)
    assert first.count == 2

    assert second.kind == "support"
    assert isclose(second.lower, 102.0)
    assert isclose(second.upper, 102.0)
    assert isclose(second.center, 102.0)
    assert second.count == 1


def test_cluster_support_and_resistance_separately() -> None:
    raw_levels = [
        RawLevel(100.0, "support", "a", "1d", "s1"),
        RawLevel(100.1, "support", "b", "1d", "s2"),
        RawLevel(104.0, "resistance", "a", "1d", "r1"),
        RawLevel(104.1, "resistance", "b", "1d", "r2"),
    ]
    zones = cluster_raw_levels_into_zones(raw_levels, zone_width=0.25)

    assert len(zones) == 2
    assert [zone.kind for zone in zones] == ["support", "resistance"]


def test_cluster_ignores_reference_levels() -> None:
    raw_levels = [
        RawLevel(100.0, "support", "a", "1d", "s1"),
        RawLevel(101.0, "reference", "pivot", "1d", "pivot"),
        RawLevel(104.0, "resistance", "a", "1d", "r1"),
    ]
    zones = cluster_raw_levels_into_zones(raw_levels, zone_width=0.5)

    assert len(zones) == 2
    assert all(zone.kind in {"support", "resistance"} for zone in zones)


def test_cluster_weighted_center_uses_source_and_timeframe_weights() -> None:
    raw_levels = [
        RawLevel(100.0, "support", "swing", "1d", "s1"),
        RawLevel(101.0, "support", "atr_band", "1h", "s2"),
    ]
    zones = cluster_raw_levels_into_zones(
        raw_levels,
        zone_width=2.0,
        source_weights={"swing": 2.0, "atr_band": 1.0},
        timeframe_weights={"1d": 2.0, "1h": 1.0},
    )

    assert len(zones) == 1
    zone = zones[0]
    assert isclose(zone.center, (100.0 * 4.0 + 101.0 * 1.0) / 5.0)
    assert isclose(zone.weight, 5.0)
    assert zone.count == 2
    assert zone.sources == ("atr_band", "swing")
    assert zone.timeframes == ("1d", "1h")


def test_cluster_requires_positive_zone_width() -> None:
    try:
        cluster_raw_levels_into_zones([], zone_width=0.0)
    except ValueError as exc:
        assert "zone_width must be positive" in str(exc)
    else:
        raise AssertionError("expected ValueError for non-positive zone_width")
