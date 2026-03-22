from market_health.risk_overlay import build_risk_overlay_state


def test_risk_overlay_unavailable_without_catastrophic_stop():
    s = build_risk_overlay_state(
        symbol="XLE",
        structure_summary={
            "support_cushion_atr": 0.9,
            "breakdown_trigger": 58.07,
        },
    )

    assert s.symbol == "XLE"
    assert s.armed is False
    assert s.catastrophic_stop is None
    assert s.status == "UNAVAILABLE"


def test_risk_overlay_armed_when_support_cushion_is_tight():
    s = build_risk_overlay_state(
        symbol="XLE",
        structure_summary={
            "catastrophic_stop_candidate": 58.07,
            "breakdown_trigger": 58.07,
            "support_cushion_atr": 0.4,
        },
    )

    assert s.armed is True
    assert s.catastrophic_stop == 58.07
    assert s.breach_level == 58.07
    assert s.status == "ARMED"


def test_risk_overlay_disarmed_when_stop_exists_but_not_tight():
    s = build_risk_overlay_state(
        symbol="XLE",
        structure_summary={
            "catastrophic_stop_candidate": 58.07,
            "breakdown_trigger": 58.07,
            "support_cushion_atr": 0.9,
        },
    )

    assert s.armed is False
    assert s.catastrophic_stop == 58.07
    assert s.breach_level == 58.07
    assert s.status == "DISARMED"
