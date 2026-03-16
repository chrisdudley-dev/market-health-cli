import json
import os
import subprocess
import sys
from pathlib import Path


def test_export_recommendations_forecast_mode_mixed_market_is_valid(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    positions_p = tmp_path / "positions.v1.json"
    forecast_p = tmp_path / "forecast_scores.v1.json"
    sectors_p = tmp_path / "market_health.sectors.json"
    out_p = tmp_path / "recommendations.v1.json"

    positions_p.write_text(
        json.dumps(
            {
                "schema": "positions.v1",
                "positions": [{"symbol": "1625.T", "market_value": 1000.0}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    forecast_p.write_text(
        json.dumps(
            {
                "schema": "forecast_scores.v1",
                "horizons_trading_days": [1, 5],
                "scores": {
                    "1625.T": {
                        "1": {"forecast_score": 0.20},
                        "5": {"forecast_score": 0.20},
                    },
                    "EWJ": {
                        "1": {"forecast_score": 0.40},
                        "5": {"forecast_score": 0.40},
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    sectors_p.write_text(
        json.dumps(
            [
                {
                    "symbol": "1625.T",
                    "market": "JP",
                    "region": "APAC",
                    "family_id": "technology",
                    "bucket_id": "jp_electric_appliances_precision",
                    "categories": {},
                },
                {
                    "symbol": "EWJ",
                    "market": "JP",
                    "region": "APAC",
                    "family_id": "broad_equity",
                    "bucket_id": "jp_broad_market",
                    "categories": {},
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["HOME"] = str(tmp_path)

    cache_dir = tmp_path / ".cache" / "jerboa"
    cache_dir.mkdir(parents=True, exist_ok=True)

    (cache_dir / "positions.v1.json").write_text(positions_p.read_text(encoding="utf-8"), encoding="utf-8")
    (cache_dir / "forecast_scores.v1.json").write_text(forecast_p.read_text(encoding="utf-8"), encoding="utf-8")
    (cache_dir / "market_health.sectors.json").write_text(sectors_p.read_text(encoding="utf-8"), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "export_recommendations_v1.py"),
            "--forecast",
            "--positions",
            str(cache_dir / "positions.v1.json"),
            "--forecast-path",
            str(cache_dir / "forecast_scores.v1.json"),
            "--out",
            str(out_p),
            "--min-improvement",
            "0.05",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "action=" in proc.stdout

    doc = json.loads(out_p.read_text(encoding="utf-8"))
    assert doc["schema"] == "recommendations.v1"
    assert doc["recommendation"]["action"] in {"SWAP", "NOOP"}
    assert isinstance(doc["recommendation"]["reason"], str) and doc["recommendation"]["reason"]

    diag = doc["recommendation"].get("diagnostics") or {}
    assert diag.get("mode") == "forecast"
