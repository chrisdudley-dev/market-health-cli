from market_health.forecast_features import rolling_correlation


def test_rolling_correlation_aligns_trailing_overlap_when_left_series_is_longer() -> (
    None
):
    got = rolling_correlation([99.0, 1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0], 3)

    assert len(got) == 4
    assert got[0] is None
    assert got[1] is None
    assert round(got[2] or 0.0, 6) == 1.0
    assert round(got[3] or 0.0, 6) == 1.0


def test_rolling_correlation_aligns_trailing_overlap_when_right_series_is_longer() -> (
    None
):
    got = rolling_correlation([1.0, 2.0, 3.0, 4.0], [99.0, 1.0, 2.0, 3.0, 4.0], 3)

    assert len(got) == 4
    assert got[0] is None
    assert got[1] is None
    assert round(got[2] or 0.0, 6) == 1.0
    assert round(got[3] or 0.0, 6) == 1.0
