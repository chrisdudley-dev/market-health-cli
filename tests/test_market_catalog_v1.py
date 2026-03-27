from pathlib import Path

from market_health.market_catalog import load_market_profile, load_symbol_catalog


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

    assert len(symbols) == 6

    ewj = next(sym for sym in symbols if sym.symbol == "EWJ")
    assert ewj.market == "JP"
    assert ewj.region == "APAC"
    assert ewj.kind == "broad_market"
    assert ewj.bucket_id == "jp_broad_market"
    assert ewj.family_id == "broad_equity"
    assert ewj.calendar_id == "JPX"
    assert ewj.currency == "JPY"
    assert ewj.taxonomy == "topix17"
    assert ewj.tradable_live is True
    assert ewj.broker_profile == "us_retail_supported"

    research_only = [sym for sym in symbols if not getattr(sym, "tradable_live", True)]
    assert len(research_only) == 5
    assert all(sym.market == "JP" for sym in research_only)
    assert all(sym.broker_profile == "research_only" for sym in research_only)
