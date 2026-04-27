from __future__ import annotations

from collections import defaultdict

from market_health.etf_universe_v1 import load_etf_universe
from market_health.universe import classify_asset_symbol, get_default_scoring_symbols


FACTOR_STYLE_SYMBOLS = {
    "SPMO",
    "MTUM",
    "QUAL",
    "SPHQ",
    "VLUE",
    "IVE",
    "RPV",
    "IWF",
    "SPYG",
    "RPG",
    "USMV",
    "SPLV",
    "RSP",
    "IWM",
    "IJR",
    "MDY",
    "IJH",
}

EXPECTED_SLEEVES = {
    "momentum": {"SPMO", "MTUM"},
    "quality": {"QUAL", "SPHQ"},
    "value": {"VLUE", "IVE", "RPV"},
    "growth": {"IWF", "SPYG", "RPG"},
    "low_volatility": {"USMV", "SPLV"},
    "equal_weight": {"RSP"},
    "size": {"IWM", "IJR", "MDY", "IJH"},
}


def _factor_rows():
    rows = load_etf_universe()
    return [
        row
        for row in rows
        if str(row.get("symbol", "")).upper() in FACTOR_STYLE_SYMBOLS
    ]


def test_factor_style_etfs_are_in_default_registry(monkeypatch):
    monkeypatch.delenv("JERBOA_ETF_UNIVERSE_JSON", raising=False)

    rows = load_etf_universe()
    by_symbol = {str(row.get("symbol", "")).upper(): row for row in rows}

    missing = sorted(FACTOR_STYLE_SYMBOLS - set(by_symbol))
    assert not missing

    for sym in FACTOR_STYLE_SYMBOLS:
        row = by_symbol[sym]
        assert row["enabled"] is True
        assert row["inverse_or_levered"] is False
        assert row["strategy_wrapper"] is False
        assert row["family"] == "factor_style"
        assert row["exposure"] == "us_factor_style_equity"
        assert str(row["overlap_key"]).startswith("factor_")
        assert row["region"] == "United States"


def test_factor_style_etfs_are_rankable_when_etf_universe_enabled(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")
    monkeypatch.delenv("JERBOA_ETF_UNIVERSE_JSON", raising=False)

    symbols = set(get_default_scoring_symbols())
    missing = sorted(FACTOR_STYLE_SYMBOLS - symbols)
    assert not missing

    meta = classify_asset_symbol("SPMO")
    assert meta.asset_type == "etf"
    assert meta.group == "ETF"
    assert meta.inverse_or_levered is False
    assert meta.strategy_wrapper is False
    assert meta.overlap_key == "factor_momentum_us_equity"


def test_factor_style_sleeves_and_overlap_groups_are_explicit(monkeypatch):
    monkeypatch.delenv("JERBOA_ETF_UNIVERSE_JSON", raising=False)

    by_sleeve: dict[str, set[str]] = defaultdict(set)
    by_overlap: dict[str, set[str]] = defaultdict(set)

    for row in _factor_rows():
        sym = str(row["symbol"]).upper()
        sleeve = str(row["sleeve"])
        overlap_key = str(row["overlap_key"])
        by_sleeve[sleeve].add(sym)
        by_overlap[overlap_key].add(sym)

    for sleeve, expected_symbols in EXPECTED_SLEEVES.items():
        assert by_sleeve[sleeve] == expected_symbols

    assert by_overlap["factor_momentum_us_equity"] == {"SPMO", "MTUM"}
    assert by_overlap["factor_quality_us_equity"] == {"QUAL", "SPHQ"}
    assert by_overlap["factor_low_volatility_us_equity"] == {"USMV", "SPLV"}
    assert by_overlap["factor_size_us_equity"] == {"IWM", "IJR", "MDY", "IJH"}


def test_factor_style_etfs_do_not_replace_existing_m40_country_etfs(monkeypatch):
    monkeypatch.delenv("JERBOA_ETF_UNIVERSE_JSON", raising=False)

    symbols = {str(row.get("symbol", "")).upper() for row in load_etf_universe()}

    existing_country_etfs = {
        "EWC",
        "EWU",
        "EWG",
        "INDA",
        "MCHI",
        "EWY",
        "EWT",
        "VNAM",
        "QAT",
        "EZA",
    }

    assert existing_country_etfs.issubset(symbols)
    assert FACTOR_STYLE_SYMBOLS.issubset(symbols)
