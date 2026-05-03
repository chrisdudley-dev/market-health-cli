from market_health.alert_detectors import (
    detect_position_inventory_changes,
    detect_position_state_changes,
)


def test_position_inventory_suppresses_first_run_alert_storm() -> None:
    alerts = detect_position_inventory_changes(
        previous_symbols=[],
        current_symbols=["SPY", "XLF"],
    )

    assert alerts == []


def test_position_inventory_can_disable_first_run_suppression() -> None:
    alerts = detect_position_inventory_changes(
        previous_symbols=[],
        current_symbols=["SPY"],
        suppress_first_run=False,
    )

    assert [a.alert_type for a in alerts] == [
        "position_added",
        "position_symbol_set_changed",
    ]
    assert alerts[0].symbol == "SPY"


def test_position_inventory_detects_new_held_position() -> None:
    alerts = detect_position_inventory_changes(
        previous_symbols=["SPY", "XLF"],
        current_symbols=["SPY", "XLF", "XLK"],
    )

    assert [a.alert_type for a in alerts] == [
        "position_added",
        "position_symbol_set_changed",
    ]
    assert alerts[0].alert_key == "position_inventory:added:XLK"
    assert alerts[0].severity == "info"
    assert alerts[0].symbol == "XLK"
    assert alerts[0].payload["previous_symbols"] == ["SPY", "XLF"]
    assert alerts[0].payload["current_symbols"] == ["SPY", "XLF", "XLK"]

    summary = alerts[1]
    assert summary.alert_type == "position_symbol_set_changed"
    assert summary.payload["added"] == ["XLK"]
    assert summary.payload["removed"] == []


def test_position_inventory_detects_removed_held_position() -> None:
    alerts = detect_position_inventory_changes(
        previous_symbols=["SPY", "XLF"],
        current_symbols=["SPY"],
    )

    assert [a.alert_type for a in alerts] == [
        "position_removed",
        "position_symbol_set_changed",
    ]
    assert alerts[0].alert_key == "position_inventory:removed:XLF"
    assert alerts[0].severity == "warning"
    assert alerts[0].symbol == "XLF"

    summary = alerts[1]
    assert summary.alert_type == "position_symbol_set_changed"
    assert summary.severity == "warning"
    assert summary.payload["added"] == []
    assert summary.payload["removed"] == ["XLF"]


def test_position_inventory_detects_add_and_remove_together() -> None:
    alerts = detect_position_inventory_changes(
        previous_symbols=["SPY", "XLF"],
        current_symbols=["SPY", "XLK"],
    )

    assert [a.alert_type for a in alerts] == [
        "position_added",
        "position_removed",
        "position_symbol_set_changed",
    ]
    assert alerts[0].symbol == "XLK"
    assert alerts[1].symbol == "XLF"
    assert alerts[2].payload["added"] == ["XLK"]
    assert alerts[2].payload["removed"] == ["XLF"]


def test_position_inventory_equal_sets_have_no_alerts() -> None:
    alerts = detect_position_inventory_changes(
        previous_symbols=["spy", " xlf ", "SPY"],
        current_symbols=["XLF", "SPY"],
    )

    assert alerts == []


def test_position_state_detects_clean_to_dmg() -> None:
    alerts = detect_position_state_changes(
        previous_states={"SPY": "clean"},
        current_states={"SPY": "DMG"},
    )

    assert len(alerts) == 1
    assert alerts[0].alert_type == "position_state_changed"
    assert alerts[0].severity == "warning"
    assert alerts[0].symbol == "SPY"
    assert alerts[0].payload["previous_state"] == "clean"
    assert alerts[0].payload["current_state"] == "DMG"
    assert alerts[0].payload["added_tags"] == ["DMG"]
    assert alerts[0].payload["removed_tags"] == []


def test_position_state_detects_dmg_to_dmg_rcl() -> None:
    alerts = detect_position_state_changes(
        previous_states={"SPY": "DMG"},
        current_states={"SPY": "DMG,RCL"},
    )

    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert alerts[0].payload["previous_state"] == "DMG"
    assert alerts[0].payload["current_state"] == "DMG,RCL"
    assert alerts[0].payload["added_tags"] == ["RCL"]
    assert alerts[0].payload["removed_tags"] == []


def test_position_state_detects_brk_and_oh_brk() -> None:
    alerts = detect_position_state_changes(
        previous_states={"SPY": "clean", "XLF": "DMG"},
        current_states={"SPY": "BRK", "XLF": "OH,BRK"},
    )

    assert [a.symbol for a in alerts] == ["SPY", "XLF"]
    assert alerts[0].payload["added_tags"] == ["BRK"]
    assert alerts[1].payload["added_tags"] == ["BRK", "OH"]
    assert all(a.severity == "warning" for a in alerts)


def test_position_state_detects_rcl_disappears() -> None:
    alerts = detect_position_state_changes(
        previous_states={"SPY": "DMG,RCL"},
        current_states={"SPY": "DMG"},
    )

    assert len(alerts) == 1
    assert alerts[0].severity == "info"
    assert alerts[0].payload["added_tags"] == []
    assert alerts[0].payload["removed_tags"] == ["RCL"]


def test_position_state_detects_damaged_to_clean() -> None:
    alerts = detect_position_state_changes(
        previous_states={"SPY": "DMG,BRK"},
        current_states={"SPY": "clean"},
    )

    assert len(alerts) == 1
    assert alerts[0].severity == "info"
    assert alerts[0].payload["previous_state"] == "BRK,DMG"
    assert alerts[0].payload["current_state"] == "clean"
    assert alerts[0].payload["removed_tags"] == ["BRK", "DMG"]


def test_position_state_ignores_formatting_only_changes() -> None:
    alerts = detect_position_state_changes(
        previous_states={"spy": "DMG, RCL", "xlf": "clean"},
        current_states={"SPY": "RCL DMG", "XLF": "OK"},
    )

    assert alerts == []


def test_position_state_ignores_symbols_not_present_in_both_snapshots() -> None:
    alerts = detect_position_state_changes(
        previous_states={"SPY": "DMG", "XLF": "BRK"},
        current_states={"SPY": "DMG,RCL", "XLK": "DMG"},
    )

    assert len(alerts) == 1
    assert alerts[0].symbol == "SPY"


def test_forecast_warning_detects_h1_and_h5_below_current() -> None:
    from market_health.alert_detectors import detect_forecast_warnings

    alerts = detect_forecast_warnings(
        symbol="spy",
        current_score=72,
        h1_score=66,
        h5_score=60,
    )

    assert [a.alert_type for a in alerts] == [
        "held_forecast_divergence",
        "held_forecast_divergence",
    ]
    assert [a.payload["triggered_rule"] for a in alerts] == ["C>H1", "C>H5"]
    assert alerts[0].symbol == "SPY"
    assert alerts[0].payload["drop"] == 6.0
    assert alerts[1].payload["drop"] == 12.0


def test_forecast_warning_current_drop_threshold_is_configurable() -> None:
    from market_health.alert_detectors import detect_forecast_warnings

    alerts = detect_forecast_warnings(
        symbol="SPY",
        current_score=72,
        h1_score=68,
        h5_score=67,
        current_drop_threshold=4,
    )

    assert [a.payload["triggered_rule"] for a in alerts] == ["C>H1", "C>H5"]


def test_forecast_warning_detects_previous_snapshot_weakening() -> None:
    from market_health.alert_detectors import detect_forecast_warnings

    alerts = detect_forecast_warnings(
        symbol="SPY",
        current_score=70,
        h1_score=60,
        h5_score=58,
        previous_h1_score=68,
        previous_h5_score=70,
        previous_drop_threshold=7,
    )

    weakened = [a for a in alerts if a.alert_type == "forecast_weakened"]
    assert [a.payload["horizon"] for a in weakened] == ["H1", "H5"]
    assert weakened[0].payload["weakening"] == 8.0
    assert weakened[1].payload["weakening"] == 12.0


def test_forecast_warning_detects_band_worsening() -> None:
    from market_health.alert_detectors import detect_forecast_warnings

    alerts = detect_forecast_warnings(
        symbol="SPY",
        current_score=72,
        h1_score=54,
        h5_score=69,
        previous_h1_score=56,
        previous_h5_score=71,
    )

    band_alerts = [a for a in alerts if a.alert_type == "forecast_band_worsened"]
    assert [a.payload["horizon"] for a in band_alerts] == ["H1", "H5"]
    assert band_alerts[0].payload["previous_band"] == "yellow"
    assert band_alerts[0].payload["current_band"] == "red"
    assert band_alerts[1].payload["previous_band"] == "green"
    assert band_alerts[1].payload["current_band"] == "yellow"


def test_forecast_warning_no_alert_when_scores_are_stable() -> None:
    from market_health.alert_detectors import detect_forecast_warnings

    alerts = detect_forecast_warnings(
        symbol="SPY",
        current_score=70,
        h1_score=68,
        h5_score=66,
        previous_h1_score=69,
        previous_h5_score=67,
    )

    assert alerts == []


def test_forecast_warning_ignores_missing_scores_and_blank_symbol() -> None:
    from market_health.alert_detectors import detect_forecast_warnings

    assert (
        detect_forecast_warnings(
            symbol="",
            current_score=70,
            h1_score=60,
            h5_score=55,
        )
        == []
    )

    assert (
        detect_forecast_warnings(
            symbol="SPY",
            current_score=None,
            h1_score=None,
            h5_score=60,
            previous_h1_score=None,
            previous_h5_score=None,
        )
        == []
    )


def test_held_forecast_divergence_detects_blend_independently() -> None:
    from market_health.alert_detectors import detect_held_forecast_divergence

    alerts = detect_held_forecast_divergence(
        symbol="SPY",
        current_score=72,
        h1_score=71,
        h5_score=70,
        blend_score=66,
    )

    assert len(alerts) == 1
    assert alerts[0].alert_type == "held_forecast_divergence"
    assert alerts[0].alert_key == "held_forecast_divergence:SPY:blend"
    assert alerts[0].payload["triggered_rule"] == "C>blend"
    assert alerts[0].payload["c_score"] == 72.0
    assert alerts[0].payload["blend_score"] == 66.0
    assert alerts[0].payload["threshold"] == 5.0


def test_held_forecast_divergence_no_alert_when_below_threshold() -> None:
    from market_health.alert_detectors import detect_held_forecast_divergence

    alerts = detect_held_forecast_divergence(
        symbol="SPY",
        current_score=72,
        h1_score=68,
        h5_score=67.1,
        blend_score=69,
        threshold=5,
    )

    assert alerts == []


def test_held_unhealthy_floor_detects_rising_but_unhealthy_scores() -> None:
    from market_health.alert_detectors import detect_held_unhealthy_floor

    alerts = detect_held_unhealthy_floor(
        symbol="SPY",
        current_score=42,
        h1_score=47,
        h5_score=51,
        blend_score=49,
        healthy_floor=55,
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_type == "held_unhealthy_floor"
    assert alert.alert_key == "held_unhealthy_floor:SPY:c-h1-h5-blend"
    assert alert.payload["symbol"] == "SPY"
    assert alert.payload["c_score"] == 42.0
    assert alert.payload["h1_score"] == 47.0
    assert alert.payload["h5_score"] == 51.0
    assert alert.payload["blend_score"] == 49.0
    assert alert.payload["healthy_floor"] == 55.0
    assert alert.payload["breached_fields"] == ["C", "H1", "H5", "blend"]


def test_held_unhealthy_floor_no_alert_when_all_scores_are_healthy() -> None:
    from market_health.alert_detectors import detect_held_unhealthy_floor

    alerts = detect_held_unhealthy_floor(
        symbol="SPY",
        current_score=56,
        h1_score=57,
        h5_score=58,
        blend_score=59,
        healthy_floor=55,
    )

    assert alerts == []


def test_held_band_state_degradation_detects_one_step_score_worsening() -> None:
    from market_health.alert_detectors import detect_held_band_state_degradation

    alerts = detect_held_band_state_degradation(
        symbol="SPY",
        previous_state="clean",
        current_state="clean",
        previous_values={"C": 72, "H1": 66, "H5": 70, "blend": 71},
        current_values={"C": 68, "H1": 66, "H5": 70, "blend": 71},
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_type == "held_band_state_degraded"
    assert alert.alert_key == "held_band_state_degradation:SPY:c"
    assert alert.payload["previous_bands"]["C"] == "green"
    assert alert.payload["current_bands"]["C"] == "yellow"
    assert alert.payload["degraded_fields"] == ["C"]
    assert alert.payload["state_degraded"] is False
    assert "C band green->yellow" in alert.payload["reason"]


def test_held_band_state_degradation_detects_severe_state_and_score_worsening() -> None:
    from market_health.alert_detectors import detect_held_band_state_degradation

    alerts = detect_held_band_state_degradation(
        symbol="SPY",
        previous_state="hold",
        current_state="unhealthy",
        previous_values={"C": 72, "H1": 70, "H5": 69, "blend": 71},
        current_values={"C": 54, "H1": 50, "H5": 52, "blend": 53},
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == "warning"
    assert alert.payload["previous_state"] == "HOLD"
    assert alert.payload["current_state"] == "UNHEALTHY"
    assert alert.payload["state_degraded"] is True
    assert alert.payload["degraded_fields"] == ["C", "H1", "H5", "blend"]
    assert alert.payload["previous_values"]["c_score"] == 72.0
    assert alert.payload["current_values"]["c_score"] == 54.0
    assert "state HOLD->UNHEALTHY" in alert.payload["reason"]


def test_held_band_state_degradation_no_alert_when_unchanged() -> None:
    from market_health.alert_detectors import detect_held_band_state_degradation

    alerts = detect_held_band_state_degradation(
        symbol="SPY",
        previous_state="caution",
        current_state="caution",
        previous_values={"C": 68, "H1": 61, "H5": 59, "blend": 63},
        current_values={"C": 66, "H1": 60, "H5": 58, "blend": 62},
    )

    assert alerts == []


def test_held_band_state_degradation_no_alert_when_improving() -> None:
    from market_health.alert_detectors import detect_held_band_state_degradation

    alerts = detect_held_band_state_degradation(
        symbol="SPY",
        previous_state="unhealthy",
        current_state="clean",
        previous_values={"C": 54, "H1": 50, "H5": 52, "blend": 53},
        current_values={"C": 68, "H1": 60, "H5": 59, "blend": 62},
    )

    assert alerts == []


def test_held_significant_score_drop_detects_c_drop() -> None:
    from market_health.alert_detectors import detect_held_significant_score_drop

    alerts = detect_held_significant_score_drop(
        symbol="SPY",
        previous_values={"C": 92, "H1": 90, "H5": 88, "blend": 89},
        current_values={"C": 82, "H1": 90, "H5": 88, "blend": 89},
        threshold=7,
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_type == "held_significant_score_drop"
    assert alert.alert_key == "held_significant_score_drop:SPY:c"
    assert alert.payload["affected_fields"] == ["C"]
    assert alert.payload["drops"]["C"] == 10.0
    assert alert.payload["previous_values"]["c_score"] == 92.0
    assert alert.payload["current_values"]["c_score"] == 82.0
    assert alert.payload["threshold"] == 7.0


def test_held_significant_score_drop_detects_h1_drop() -> None:
    from market_health.alert_detectors import detect_held_significant_score_drop

    alerts = detect_held_significant_score_drop(
        symbol="SPY",
        previous_values={"C": 82, "H1": 90, "H5": 88, "blend": 89},
        current_values={"C": 82, "H1": 78, "H5": 88, "blend": 89},
        threshold=7,
    )

    assert len(alerts) == 1
    assert alerts[0].payload["affected_fields"] == ["H1"]
    assert alerts[0].payload["drops"]["H1"] == 12.0


def test_held_significant_score_drop_detects_h5_drop() -> None:
    from market_health.alert_detectors import detect_held_significant_score_drop

    alerts = detect_held_significant_score_drop(
        symbol="SPY",
        previous_values={"C": 82, "H1": 90, "H5": 88, "blend": 89},
        current_values={"C": 82, "H1": 90, "H5": 76, "blend": 89},
        threshold=7,
    )

    assert len(alerts) == 1
    assert alerts[0].payload["affected_fields"] == ["H5"]
    assert alerts[0].payload["drops"]["H5"] == 12.0


def test_held_significant_score_drop_detects_blend_drop() -> None:
    from market_health.alert_detectors import detect_held_significant_score_drop

    alerts = detect_held_significant_score_drop(
        symbol="SPY",
        previous_values={"C": 82, "H1": 90, "H5": 88, "blend": 89},
        current_values={"C": 82, "H1": 90, "H5": 88, "blend": 80},
        threshold=7,
    )

    assert len(alerts) == 1
    assert alerts[0].payload["affected_fields"] == ["blend"]
    assert alerts[0].payload["drops"]["blend"] == 9.0


def test_held_significant_score_drop_no_alert_below_threshold() -> None:
    from market_health.alert_detectors import detect_held_significant_score_drop

    alerts = detect_held_significant_score_drop(
        symbol="SPY",
        previous_values={"C": 92, "H1": 90, "H5": 88, "blend": 89},
        current_values={"C": 86, "H1": 84, "H5": 82, "blend": 83},
        threshold=7,
    )

    assert alerts == []
