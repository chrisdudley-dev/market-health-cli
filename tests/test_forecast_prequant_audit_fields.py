from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe


VALIDATOR = Path("scripts/validate_forecast_scores_v1.py")


def _ohlcv_trend(n: int = 80) -> OHLCV:
    close = [100.0 + (i * 0.25) for i in range(n)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    vol = [1_000_000.0 for _ in close]
    return OHLCV(close=close, high=high, low=low, volume=vol)


def test_forecast_checks_emit_prequant_audit_fields() -> None:
    series = _ohlcv_trend()
    scores = compute_forecast_universe(
        universe={"SPY": series, "XLK": series, "XLF": series},
        spy=series,
        horizons_trading_days=(1, 5),
    )

    check = scores["SPY"][1]["categories"]["A"]["checks"][0]

    assert check["source_quality"] in {"real", "proxy", "neutral", "disabled"}
    assert isinstance(check["fallback_used"], bool)
    assert isinstance(check["raw_inputs"], dict)
    assert "u" in check
    assert check["u"] is None or isinstance(check["u"], (int, float))
    assert isinstance(check["cutoffs"], dict)
    assert isinstance(check["orientation"], str)
    assert check["orientation"]
    assert "margin_to_flip" in check


def test_validate_forecast_scores_prints_symbol_horizon_audit(tmp_path: Path) -> None:
    series = _ohlcv_trend()
    scores = compute_forecast_universe(
        universe={"SPY": series, "XLK": series, "XLF": series},
        spy=series,
        horizons_trading_days=(1, 5),
    )

    doc = {
        "schema": "forecast_scores.v1",
        "asof": "2026-05-02T00:00:00Z",
        "horizons_trading_days": [1, 5],
        "scores": scores,
    }
    p = tmp_path / "forecast_scores.v1.json"
    p.write_text(json.dumps(doc), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--path",
            str(p),
            "--audit-symbol",
            "SPY",
            "--audit-horizons",
            "1,5",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "OK: forecast_scores.v1 valid" in proc.stdout
    assert "forecast-audit symbol=SPY horizon=1" in proc.stdout
    assert "forecast-audit symbol=SPY horizon=5" in proc.stdout
    assert "source_quality=" in proc.stdout
    assert "fallback_used=" in proc.stdout
    assert "raw_inputs=" in proc.stdout
    assert "margin_to_flip=" in proc.stdout
