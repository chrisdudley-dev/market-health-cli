from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from market_health.forecast_features import OHLCV
from market_health.forecast_input_inventory import forecast_input_inventory
from market_health.forecast_score_provider import compute_forecast_universe


VALIDATOR = Path("scripts/validate_forecast_scores_v1.py")


def _series() -> OHLCV:
    close = [100.0 + i * 0.25 for i in range(90)]
    return OHLCV(
        close=close,
        high=[c + 1.0 for c in close],
        low=[c - 1.0 for c in close],
        volume=[1_000_000.0 for _ in close],
    )


def test_inventory_covers_known_upstream_dependencies() -> None:
    rows = forecast_input_inventory()
    by_check = {row["check"]: row for row in rows}

    for check in ["A2", "C4", "D1", "E2", "E5", "E6"]:
        assert check in by_check

    allowed = {
        "implement now",
        "proxy intentionally",
        "neutral intentionally",
        "disable until available",
    }

    for row in rows:
        assert row["current_handling"] in allowed
        assert row["source_quality_when_missing"] in {
            "real",
            "proxy",
            "neutral",
            "disabled",
        }
        assert row["dependency"]
        assert row["missing_behavior"]


def test_validator_prints_input_inventory(tmp_path: Path) -> None:
    series = _series()
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
        [sys.executable, str(VALIDATOR), "--path", str(p), "--input-inventory"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "forecast-input-inventory" in proc.stdout
    assert "A2" in proc.stdout
    assert "C4" in proc.stdout
    assert "D1" in proc.stdout
    assert "VIX" in proc.stdout
    assert "flow.v1" in proc.stdout
    assert "iv.v1" in proc.stdout
