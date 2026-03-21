from math import isclose

from market_health.structure_engine import (
    NormalizedLevel,
    RawLevel,
    normalize_distance_atr,
    normalize_distance_sigma,
    normalize_raw_level,
    normalize_raw_levels,
)


def test_normalize_distance_atr_support_and_resistance_signs() -> None:
    assert isclose(normalize_distance_atr(price=100.0, level=98.0, atr=2.0), 1.0)
    assert isclose(normalize_distance_atr(price=100.0, level=102.0, atr=2.0), -1.0)


def test_normalize_distance_atr_invalid_inputs_return_none() -> None:
    assert normalize_distance_atr(price=100.0, level=98.0, atr=0.0) is None
    assert normalize_distance_atr(price=100.0, level=98.0, atr=None) is None
    assert normalize_distance_atr(price=None, level=98.0, atr=2.0) is None


def test_normalize_distance_sigma_support_and_resistance_signs() -> None:
    assert isclose(
        normalize_distance_sigma(
            price=100.0,
            level=98.0,
            close=100.0,
            realized_vol=0.02,
        ),
        1.0,
    )
    assert isclose(
        normalize_distance_sigma(
            price=100.0,
            level=102.0,
            close=100.0,
            realized_vol=0.02,
        ),
        -1.0,
    )


def test_normalize_distance_sigma_invalid_inputs_return_none() -> None:
    assert (
        normalize_distance_sigma(
            price=100.0,
            level=98.0,
            close=100.0,
            realized_vol=0.0,
        )
        is None
    )
    assert (
        normalize_distance_sigma(
            price=100.0,
            level=98.0,
            close=0.0,
            realized_vol=0.02,
        )
        is None
    )
    assert (
        normalize_distance_sigma(
            price=None,
            level=98.0,
            close=100.0,
            realized_vol=0.02,
        )
        is None
    )


def test_normalize_raw_level_returns_both_distances() -> None:
    raw = RawLevel(
        value=98.0,
        kind="support",
        source="test",
        timeframe="1d",
        label="test_support",
    )
    normalized = normalize_raw_level(
        raw,
        price=100.0,
        atr=2.0,
        close=100.0,
        realized_vol=0.02,
    )
    assert isinstance(normalized, NormalizedLevel)
    assert normalized.raw_level.label == "test_support"
    assert isclose(normalized.distance_atr, 1.0)
    assert isclose(normalized.distance_sigma, 1.0)


def test_normalize_raw_levels_preserves_order() -> None:
    raw_levels = [
        RawLevel(
            value=98.0,
            kind="support",
            source="test",
            timeframe="1d",
            label="a",
        ),
        RawLevel(
            value=102.0,
            kind="resistance",
            source="test",
            timeframe="1d",
            label="b",
        ),
    ]
    normalized = normalize_raw_levels(
        raw_levels,
        price=100.0,
        atr=2.0,
        close=100.0,
        realized_vol=0.02,
    )
    assert [item.raw_level.label for item in normalized] == ["a", "b"]
    assert isclose(normalized[0].distance_atr, 1.0)
    assert isclose(normalized[1].distance_atr, -1.0)
