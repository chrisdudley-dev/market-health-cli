from __future__ import annotations

from market_health.etf_universe_v1 import load_etf_universe
from market_health.universe import classify_asset_symbol, get_default_scoring_symbols


GLOBAL_BROAD_MARKET_SYMBOLS = {
    "EWC",
    "EWW",
    "EWZ",
    "ECH",
    "EPU",
    "ARGT",
    "EWU",
    "EWG",
    "EWQ",
    "EWI",
    "EWP",
    "EWL",
    "EWN",
    "EWD",
    "EDEN",
    "EFNL",
    "EIRL",
    "EWO",
    "EWK",
    "ENOR",
    "EPOL",
    "TUR",
    "GREK",
    "EWA",
    "EWH",
    "INDA",
    "MCHI",
    "EWY",
    "EWT",
    "EWS",
    "EWM",
    "EIDO",
    "THD",
    "EPHE",
    "ENZL",
    "VNAM",
    "EIS",
    "KSA",
    "QAT",
    "UAE",
    "EZA",
}


def test_global_broad_market_etfs_are_in_default_registry(monkeypatch):
    monkeypatch.delenv("JERBOA_ETF_UNIVERSE_JSON", raising=False)

    rows = load_etf_universe()
    by_symbol = {str(row.get("symbol", "")).upper(): row for row in rows}

    missing = sorted(GLOBAL_BROAD_MARKET_SYMBOLS - set(by_symbol))
    assert not missing

    for sym in GLOBAL_BROAD_MARKET_SYMBOLS:
        row = by_symbol[sym]
        assert row["enabled"] is True
        assert row["inverse_or_levered"] is False
        assert row["strategy_wrapper"] is False
        assert row["family"] == "global_broad_market"
        assert row["exposure"] == "single_country_broad_equity"
        assert str(row["overlap_key"]).startswith("country_")


def test_global_broad_market_etfs_are_rankable_when_etf_universe_enabled(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")
    monkeypatch.delenv("JERBOA_ETF_UNIVERSE_JSON", raising=False)

    symbols = set(get_default_scoring_symbols())
    missing = sorted(GLOBAL_BROAD_MARKET_SYMBOLS - symbols)
    assert not missing

    meta = classify_asset_symbol("INDA")
    assert meta.asset_type == "etf"
    assert meta.group == "ETF"
    assert meta.inverse_or_levered is False
    assert meta.strategy_wrapper is False
    assert meta.overlap_key == "country_india"


def test_global_broad_market_etfs_do_not_replace_existing_etfs(monkeypatch):
    monkeypatch.delenv("JERBOA_ETF_UNIVERSE_JSON", raising=False)

    symbols = {str(row.get("symbol", "")).upper() for row in load_etf_universe()}

    existing_etfs = {
        "IBIT",
        "BITI",
        "SBIT",
        "BTCI",
        "QYLD",
        "JEPI",
        "BLOK",
        "BITC",
        "ETHA",
        "BKCH",
    }

    assert existing_etfs.issubset(symbols)
    assert GLOBAL_BROAD_MARKET_SYMBOLS.issubset(symbols)
