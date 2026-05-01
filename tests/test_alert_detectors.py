from market_health.alert_detectors import detect_position_inventory_changes


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
