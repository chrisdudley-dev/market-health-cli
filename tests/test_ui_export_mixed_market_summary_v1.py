import json
import os
import subprocess
import sys
from pathlib import Path


def test_ui_export_summary_reports_mixed_markets(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cache_dir = tmp_path / ".cache" / "jerboa"
    state_dir = cache_dir / "state"
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    (cache_dir / "market_health.sectors.json").write_text(
        json.dumps(
            [
                {"symbol": "XLU", "market": "US", "region": "NA", "categories": {}},
                {"symbol": "1625.T", "market": "JP", "region": "APAC", "categories": {}},
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (cache_dir / "positions.v1.json").write_text(
        json.dumps(
            {
                "schema": "positions.v1",
                "positions": [
                    {"symbol": "XLU", "market_value": 1000.0},
                    {"symbol": "1625.T", "market_value": 1000.0},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (cache_dir / "environment.v1.json").write_text(
        json.dumps({"schema": "environment.v1", "rows": []}, indent=2) + "\n",
        encoding="utf-8",
    )

    (state_dir / "market_health_refresh_all.state.json").write_text(
        json.dumps(
            {
                "schema": "jerboa.market_health_refresh_all.state.v1",
                "status": "ok",
                "reason": "test",
                "changed": {"market": 1, "positions": 1},
                "rc": {"market": 0, "positions": 0},
                "forced": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = str(repo_root)

    subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "ui_export_ui_contract_v1.py"),
        ],
        check=True,
        env=env,
        cwd=repo_root,
    )

    out = json.loads((cache_dir / "market_health.ui.v1.json").read_text(encoding="utf-8"))
    summary = out["summary"]

    assert summary["mixed_markets"] is True
    assert summary["markets_present"] == ["JP", "US"]
    assert summary["regions_present"] == ["APAC", "NA"]
