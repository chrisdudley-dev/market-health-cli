import json
import os
import subprocess
import sys
from pathlib import Path


def test_pm13_export_preserves_forecast_selected_pair_and_candidate_pairs(
    tmp_path: Path,
):
    forecast_scores = {
        "schema": "forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "scores": {
            "AAA": {
                "1": {"forecast_score": 0.20},
                "5": {"forecast_score": 0.20},
            },
            "BBB": {
                "1": {"forecast_score": 0.45},
                "5": {"forecast_score": 0.45},
            },
            "DDD": {
                "1": {"forecast_score": 0.60},
                "5": {"forecast_score": 0.60},
            },
        },
    }

    positions = {
        "schema": "positions.v1",
        "positions": [
            {"symbol": "AAA", "market_value": 100.0},
            {"symbol": "BBB", "market_value": 900.0},
        ],
    }

    forecast_p = tmp_path / "forecast.json"
    positions_p = tmp_path / "positions.json"
    out_p = tmp_path / "recommendations.json"

    forecast_p.write_text(json.dumps(forecast_scores), encoding="utf-8")
    positions_p.write_text(json.dumps(positions), encoding="utf-8")

    # Deterministic exporter environment:
    # - isolated HOME/JERBOA_HOME_WIN so no prior state or cache leaks in
    # - shim compute_scores so exporter never hits live data
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "market_health").mkdir()
    (shim / "market_health" / "__init__.py").write_text(
        "from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )
    (shim / "market_health" / "engine.py").write_text(
        """def compute_scores(*args, **kwargs):
    return [
        {"symbol": "AAA", "categories": {"A": {"checks": [{"label": "c", "score": 0}]}}},
        {"symbol": "BBB", "categories": {"A": {"checks": [{"label": "c", "score": 1}]}}},
        {"symbol": "DDD", "categories": {"A": {"checks": [{"label": "c", "score": 2}]}}},
    ]
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["JERBOA_HOME_WIN"] = str(tmp_path)
    env["PYTHONPATH"] = str(shim) + os.pathsep + str(Path.cwd())

    subprocess.run(
        [
            sys.executable,
            "scripts/export_recommendations_v1.py",
            "--positions",
            str(positions_p),
            "--forecast",
            "--forecast-path",
            str(forecast_p),
            "--out",
            str(out_p),
            "--min-improvement",
            "0.01",
            "--max-weight",
            "1.0",
            "--min-distinct",
            "1",
            "--hhi-cap",
            "1.0",
            "--quiet",
        ],
        check=True,
        env=env,
    )

    doc = json.loads(out_p.read_text(encoding="utf-8"))
    rec = doc["recommendation"]
    diag = rec["diagnostics"]

    assert rec["action"] == "SWAP"
    assert "selected_pair" in diag
    assert "candidate_pairs" in diag

    selected = diag["selected_pair"]
    assert selected["from_symbol"] == rec["from_symbol"]
    assert selected["to_symbol"] == rec["to_symbol"]
    assert selected["decision_metric"] == diag["decision_metric"]
    assert selected["edges_by_h"] == diag["edges_by_h"]

    assert isinstance(diag["candidate_pairs"], list)
    assert len(diag["candidate_pairs"]) >= 1
