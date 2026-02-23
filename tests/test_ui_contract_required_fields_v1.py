import json
import os
import subprocess
import tempfile
from pathlib import Path
from shutil import copyfile


def _run_ui_export_from_fixture(tmp_home: Path, scenario_dir: Path) -> dict:
    cache = tmp_home / ".cache" / "jerboa"
    (cache / "state").mkdir(parents=True, exist_ok=True)

    for f in scenario_dir.glob("*.json"):
        copyfile(f, cache / f.name)
    for f in (scenario_dir / "state").glob("*.json"):
        copyfile(f, cache / "state" / f.name)

    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    env["QUIET"] = "1"
    env.setdefault("JERBOA_PYTHON", "python")

    subprocess.run(
        ["bash", "scripts/jerboa/bin/jerboa-market-health-ui-export"],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    p = cache / "market_health.ui.v1.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_ui_contract_required_fields_and_types():
    scenario = Path("tests/fixtures/scenarios/bullish/jerboa_cache")
    assert scenario.exists()

    tmp_home = Path(tempfile.mkdtemp())
    contract = _run_ui_export_from_fixture(tmp_home, scenario)

    assert isinstance(contract, dict)
    for k in ("schema", "asof", "meta", "summary", "data"):
        assert k in contract

    assert contract["schema"] in {"jerboa.market_health.ui.v1", "market_health.ui.v1"}
    if "generated_at" in contract:
        assert isinstance(contract["generated_at"], str)
    assert isinstance(contract["asof"], str)

    meta = contract["meta"]
    summary = contract["summary"]
    data = contract["data"]
    assert isinstance(meta, dict)
    assert isinstance(summary, dict)
    assert isinstance(data, dict)

    # Meta blocks must exist and be well-typed.
    # (These are the stable cache-backed artifacts in the UI contract.)
    for k in (
        "environment",
        "positions",
        "sectors",
        "state",
        "recommendations",
        "events_provider",
    ):
        assert k in meta
        m = meta[k]
        assert isinstance(m, dict)
        assert isinstance(m.get("path"), str)
        assert isinstance(m.get("exists"), bool)

    # Summary must provide stable rollups + recommendation status.
    assert isinstance(summary.get("positions_count"), int)
    if "sectors_count" in summary:
        assert isinstance(summary.get("sectors_count"), int)
    assert isinstance(summary.get("events_count"), int)
    assert summary.get("recommendations_status") in {"ok", "missing", "unreadable"}

    # Data must include the main payload keys used by the UI.
    for k in (
        "environment",
        "positions",
        "sectors",
        "state",
        "recommendations",
    ):
        assert k in data

    assert isinstance(data["sectors"], list)
    assert data["environment"] is None or isinstance(data["environment"], dict)
    assert data["positions"] is None or isinstance(data["positions"], dict)
    assert data["state"] is None or isinstance(data["state"], dict)
    assert data["recommendations"] is None or isinstance(data["recommendations"], dict)
