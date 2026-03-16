import json
import os
import subprocess
import sys
from pathlib import Path


def test_ui_export_smoke_surfaces_non_us_market_metadata(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cache_dir = tmp_path / ".cache" / "jerboa"
    state_dir = cache_dir / "state"
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    fixture_sectors = repo_root / "tests" / "fixtures" / "non_us_market_slice_ewj.sectors.json"
    (cache_dir / "market_health.sectors.json").write_text(
        fixture_sectors.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    (cache_dir / "positions.v1.json").write_text(
        json.dumps(
            {
                "schema": "positions.v1",
                "positions": [{"symbol": "EWJ", "market_value": 1000.0}],
            },
            indent=2,
        ) + "\n",
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
        ) + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = str(repo_root)

    subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "ui_export_ui_contract_v1.py")],
        check=True,
        env=env,
        cwd=repo_root,
    )

    out = json.loads((cache_dir / "market_health.ui.v1.json").read_text(encoding="utf-8"))

    ewj = next(row for row in out["data"]["sectors"] if row["symbol"] == "EWJ")
    assert ewj["market"] == "JP"
    assert ewj["region"] == "APAC"
    assert ewj["benchmark_symbol"] == "TOPIX"
    assert ewj["calendar_id"] == "JPX"
    assert ewj["currency"] == "JPY"
    assert ewj["taxonomy"] == "topix17"

    sample_meta = out["summary"]["symbols_sample_meta"]
    assert len(sample_meta) == 1
    assert sample_meta[0]["symbol"] == "EWJ"
    assert sample_meta[0]["market"] == "JP"
