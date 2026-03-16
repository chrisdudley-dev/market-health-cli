from pathlib import Path

from market_health.market_catalog import (
    load_market_profile,
    load_symbol_catalog,
    load_taxonomy_bridge,
    validate_symbol_against_bridge,
    validate_symbol_against_market,
)


def test_japan_market_profile_symbol_catalog_and_bridge_load() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    market = load_market_profile(repo_root / "config" / "markets" / "jp.yaml")
    symbols = load_symbol_catalog(repo_root / "config" / "symbols" / "global_markets.yaml")
    bridge = load_taxonomy_bridge(repo_root / "config" / "taxonomy" / "jp_topix17_bridge.yaml")

    assert market.market == "JP"
    assert market.region == "APAC"
    assert market.calendar_id == "JPX"
    assert market.broad_benchmark == "TOPIX"

    assert len(symbols) == 6
    assert sorted(s.symbol for s in symbols) == [
        "1624.T",
        "1625.T",
        "1627.T",
        "1632.T",
        "1633.T",
        "EWJ",
    ]

    assert sorted(bridge.keys()) == [
        "jp_broad_market",
        "jp_electric_appliances_precision",
        "jp_electric_power_gas",
        "jp_financials_ex_banks",
        "jp_machinery",
        "jp_real_estate",
    ]

    for sym in symbols:
        validate_symbol_against_market(sym, market)
        validate_symbol_against_bridge(sym, bridge)
