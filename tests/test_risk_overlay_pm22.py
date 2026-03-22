from market_health.risk_overlay import (
    build_confirmed_risk_overlay_state,
    build_risk_overlay_state,
    confirm_overlay_breach,
)


def test_confirm_overlay_breach_requires_armed_overlay():
    overlay = build_risk_overlay_state(
        symbol="XLE",
        structure_summary={
            "catastrophic_stop_candidate": 58.07,
            "breakdown_trigger": 58.07,
            "support_cushion_atr": 0.9,
        },
    )

    assert (
        confirm_overlay_breach(
            overlay=overlay,
            close_price=57.5,
            prior_close_price=57.6,
        )
        is False
    )


def test_confirm_overlay_breach_requires_two_closes_by_default():
    overlay = build_risk_overlay_state(
        symbol="XLE",
        structure_summary={
            "catastrophic_stop_candidate": 58.07,
            "breakdown_trigger": 58.07,
            "support_cushion_atr": 0.4,
        },
    )

    assert overlay.armed is True
    assert (
        confirm_overlay_breach(
            overlay=overlay,
            close_price=57.5,
            prior_close_price=58.2,
        )
        is False
    )
    assert (
        confirm_overlay_breach(
            overlay=overlay,
            close_price=57.5,
            prior_close_price=57.8,
        )
        is True
    )


def test_confirm_overlay_breach_single_close_mode():
    overlay = build_risk_overlay_state(
        symbol="XLE",
        structure_summary={
            "catastrophic_stop_candidate": 58.07,
            "breakdown_trigger": 58.07,
            "support_cushion_atr": 0.4,
        },
    )

    assert (
        confirm_overlay_breach(
            overlay=overlay,
            close_price=57.5,
            confirm_closes=1,
        )
        is True
    )


def test_build_confirmed_overlay_state_marks_breached():
    state = build_confirmed_risk_overlay_state(
        symbol="XLE",
        structure_summary={
            "catastrophic_stop_candidate": 58.07,
            "breakdown_trigger": 58.07,
            "support_cushion_atr": 0.4,
        },
        close_price=57.5,
        prior_close_price=57.8,
    )

    assert state.status == "BREACHED"
    assert state.armed is True
    assert state.breach_level == 58.07
