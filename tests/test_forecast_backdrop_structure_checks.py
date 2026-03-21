from market_health.forecast_checks_b_backdrop import (
    b2_follow_through_setup,
    b4_support_cushion,
    compute_b_checks,
)


def test_b4_support_cushion_uses_structure_value_when_present() -> None:
    check = b4_support_cushion(
        close=100.0,
        ema20=98.0,
        atrp14=1.0,
        structure_support_cushion_atr=1.6,
    )
    assert check.score == 2
    assert check.metrics["structure_support_cushion_atr"] == 1.6
    assert check.metrics["cushion_proxy"] == 1.6


def test_b4_support_cushion_falls_back_to_proxy_when_structure_missing() -> None:
    check = b4_support_cushion(
        close=100.0,
        ema20=99.0,
        atrp14=1.0,
        structure_support_cushion_atr=None,
    )
    assert check.score in (0, 1, 2)
    assert "cushion_proxy" in check.metrics


def test_b2_follow_through_setup_uses_structure_bucket_when_present() -> None:
    check = b2_follow_through_setup(
        close=100.0,
        hi20=101.0,
        clv=0.0,
        structure_overhead_resistance_atr=0.3,
        structure_breakout_quality_bucket=2,
    )
    assert check.score == 2
    assert check.metrics["structure_breakout_quality_bucket"] == 2


def test_compute_b_checks_still_returns_six_checks() -> None:
    checks = compute_b_checks(
        close=100.0,
        ema20=99.0,
        sma50=98.0,
        slope_close_10=0.01,
        hi20=100.0,
        clv=0.4,
        rs_slope_10=0.01,
        rs_z_20=0.5,
        atrp14=1.0,
        up_down_vol_ratio_20=1.2,
        ext_z_20=1.0,
        vol_rank_20=0.5,
        structure_support_cushion_atr=1.2,
        structure_overhead_resistance_atr=0.4,
        structure_breakout_quality_bucket=2,
    )
    assert len(checks) == 6
    assert checks[1].label == "Follow-Through Setup"
    assert checks[3].label == "Support Cushion"
