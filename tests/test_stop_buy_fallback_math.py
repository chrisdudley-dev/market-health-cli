from __future__ import annotations

from pathlib import Path


def test_dashboard_legacy_uses_clustered_stop_buy_with_fallback_math():
    source = Path("market_health/dashboard_legacy.py").read_text(encoding="utf-8")

    assert "atr = tr.rolling(14, min_periods=5).mean()" in source

    assert "fallback_stop = recent_low - (0.25 * atr_last)" in source
    assert "fallback_buy = recent_high + (0.25 * atr_last)" in source

    assert "generate_stop_buy_candidates" in source
    assert "strongest_stop_buy_clusters" in source
    assert "min_cluster_size=2" in source

    assert 'stop_source = "clustered_floor"' in source
    assert 'buy_source = "clustered_ceiling"' in source
    assert 'stop_source = "recent_low_atr_fallback"' in source
    assert 'buy_source = "recent_high_atr_fallback"' in source

    assert '"stop": round(stop, 6)' in source
    assert '"stop_candidate": round(stop, 6)' in source
    assert '"catastrophic_stop_candidate": round(stop, 6)' in source
    assert '"buy": round(buy, 6)' in source
    assert '"buy_candidate": round(buy, 6)' in source
    assert '"stop_buy_candidate": round(buy, 6)' in source
    assert '"breakout_trigger": round(buy, 6)' in source


def test_dashboard_table_keeps_simple_stop_and_buy_columns():
    source = Path("market_health/dashboard_legacy.py").read_text(encoding="utf-8")

    assert 'tbl.add_column("Stop"' in source
    assert 'tbl.add_column("Buy"' in source
    assert 'tbl.add_column("Stop Source"' not in source
    assert 'tbl.add_column("Buy Source"' not in source
