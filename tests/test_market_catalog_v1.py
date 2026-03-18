from pathlib import Path

from market_health.market_catalog import (
    load_market_profile,
    load_symbol_catalog,
    validate_symbol_against_market,
)


def test_japan_market_profile_and_symbol_catalog_load() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    market = load_market_profile(repo_root / "config" / "markets" / "jp.yaml")
    symbols = load_symbol_catalog(
        repo_root / "config" / "symbols" / "global_markets.yaml"
    )

    assert market.market == "JP"
    assert market.region == "APAC"
    assert market.calendar_id == "JPX"
    assert market.broad_benchmark == "TOPIX"

    assert len(symbols) == 1
    sym = symbols[0]
    assert sym.symbol == "JP_BROAD"
    assert sym.family_id == "broad_equity"
    assert sym.calendar_id == "JPX"

    validate_symbol_against_market(sym, market)
