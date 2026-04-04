import importlib

import market_health.universe as universe
import market_health.engine as engine


def test_default_scoring_symbols_includes_precious_by_default(monkeypatch):
    monkeypatch.delenv("MH_ENABLE_PRECIOUS_METALS", raising=False)
    syms = universe.get_default_scoring_symbols()
    assert "GLDM" in syms
    assert "GLTR" in syms
    assert "XLE" in syms


def test_default_scoring_symbols_excludes_precious_when_disabled(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_PRECIOUS_METALS", "0")
    syms = universe.get_default_scoring_symbols()
    assert "GLDM" not in syms
    assert "GLTR" not in syms
    assert "XLE" in syms


def test_engine_sectors_default_respects_feature_flag_on_reload(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_PRECIOUS_METALS", "1")
    importlib.reload(universe)
    importlib.reload(engine)
    assert "GLDM" in engine.SECTORS_DEFAULT
    assert "GLTR" in engine.SECTORS_DEFAULT


def test_etf_universe_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MH_ENABLE_ETF_UNIVERSE", raising=False)
    assert universe.etf_universe_enabled() is False
    assert "IBIT" not in universe.get_configured_etf_symbols()
    meta = universe.classify_asset_symbol("IBIT")
    assert meta.asset_type == "unsupported"
    assert meta.group == "UNSUPPORTED"


def test_etf_universe_enabled_exposes_configured_symbols(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")
    syms = universe.get_configured_etf_symbols()
    assert "IBIT" in syms
    assert "ETHA" in syms
    assert "QYLD" in syms


def test_classify_asset_symbol_recognizes_enabled_etf(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")
    meta = universe.classify_asset_symbol("IBIT")
    assert meta.asset_type == "etf"
    assert meta.group == "ETF"
