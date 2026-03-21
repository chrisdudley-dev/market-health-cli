from market_health.forecast_checks_d_danger import (
    compute_d_checks,
    d5_drawdown_vulnerability,
    d6_risk_reward_feasibility,
)


def test_d5_drawdown_vulnerability_uses_structure_inputs() -> None:
    check = d5_drawdown_vulnerability(
        close=100.0,
        lo20=95.0,
        atrp14=2.0,
        structure_support_cushion_atr=0.4,
        structure_breakdown_risk_bucket=2,
    )
    assert check.score == 0
    assert check.metrics["structure_support_cushion_atr"] == 0.4
    assert check.metrics["structure_breakdown_risk_bucket"] == 2


def test_d6_risk_reward_feasibility_uses_structure_inputs() -> None:
    check = d6_risk_reward_feasibility(
        atrp14=3.0,
        support_cushion_proxy=1.2,
        corr20=0.9,
        structure_support_cushion_atr=0.4,
        structure_breakdown_risk_bucket=2,
    )
    assert check.score == 0
    assert check.metrics["effective_cushion"] == 0.4


def test_d6_risk_reward_feasibility_falls_back_when_structure_missing() -> None:
    check = d6_risk_reward_feasibility(
        atrp14=2.0,
        support_cushion_proxy=1.0,
        corr20=0.5,
        structure_support_cushion_atr=None,
        structure_breakdown_risk_bucket=None,
    )
    assert check.score in (0, 1, 2)
    assert check.metrics["effective_cushion"] == 1.0


def test_compute_d_checks_still_returns_six_checks() -> None:
    checks = compute_d_checks(
        H=5,
        atrp14=2.0,
        atrp_slope_10=0.1,
        bb_width=5.0,
        returns=[0.0] * 40,
        calendar={"catalysts_in_window": False},
        corr5=0.5,
        corr20=0.4,
        volume=[1000.0] * 40,
        close=100.0,
        lo20=95.0,
        support_cushion_proxy=1.0,
        structure_support_cushion_atr=0.8,
        structure_breakdown_risk_bucket=1,
    )
    assert len(checks) == 6
    assert checks[4].label == "Drawdown Vulnerability"
    assert checks[5].label == "Risk/Reward Feasibility"
