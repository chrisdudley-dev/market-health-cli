import importlib

import market_health.universe as universe
import market_health.engine as engine


def test_default_scoring_symbols_excludes_precious_by_default(monkeypatch):
    monkeypatch.delenv("MH_ENABLE_PRECIOUS_METALS", raising=False)
    syms = universe.get_default_scoring_symbols()
    assert "GLDM" not in syms
    assert "GLTR" not in syms
    assert "XLE" in syms


def test_default_scoring_symbols_includes_precious_when_enabled(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_PRECIOUS_METALS", "1")
    syms = universe.get_default_scoring_symbols()
    assert "GLDM" in syms
    assert "GLTR" in syms
    assert "XLE" in syms


def test_engine_sectors_default_respects_feature_flag_on_reload(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_PRECIOUS_METALS", "1")
    importlib.reload(universe)
    importlib.reload(engine)
    assert "GLDM" in engine.SECTORS_DEFAULT
    assert "GLTR" in engine.SECTORS_DEFAULT
