from market_health.market_catalog import (
    get_taxonomy_bridge_entry_for_symbol,
    get_taxonomy_bridge_for_market,
)


def test_jp_taxonomy_bridge_entries_are_explicit_and_reviewable() -> None:
    bridge = get_taxonomy_bridge_for_market("JP")

    assert sorted(bridge.keys()) == [
        "jp_broad_market",
        "jp_electric_appliances_precision",
        "jp_electric_power_gas",
        "jp_financials_ex_banks",
        "jp_machinery",
        "jp_real_estate",
    ]

    assert bridge["jp_machinery"].family_id == "industrials"
    assert bridge["jp_electric_appliances_precision"].family_id == "technology"
    assert bridge["jp_electric_power_gas"].family_id == "utilities"
    assert bridge["jp_financials_ex_banks"].family_id == "financials"
    assert bridge["jp_real_estate"].family_id == "real_estate"


def test_bridge_entry_lookup_by_symbol() -> None:
    assert get_taxonomy_bridge_entry_for_symbol("1625.T").family_id == "technology"
    assert get_taxonomy_bridge_entry_for_symbol("1632.T").family_id == "financials"
    assert get_taxonomy_bridge_entry_for_symbol("1633.T").family_id == "real_estate"
