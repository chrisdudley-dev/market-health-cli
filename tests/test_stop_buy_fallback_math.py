from __future__ import annotations

from pathlib import Path


def test_dashboard_legacy_documents_current_stop_buy_fallback_math():
    source = Path("market_health/dashboard_legacy.py").read_text(encoding="utf-8")

    assert "atr = tr.rolling(14, min_periods=5).mean()" in source
    assert (
        "support_cushion_atr = max(0.0, (last_close - recent_low) / atr_last)" in source
    )
    assert (
        "overhead_resistance_atr = max(0.0, (recent_high - last_close) / atr_last)"
        in source
    )
    assert "stop = recent_low - (0.25 * atr_last)" in source
    assert "buy = recent_high + (0.25 * atr_last)" in source

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
