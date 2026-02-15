from pathlib import Path
import json
import os
import subprocess

def _load_contract_from_cache(home: Path) -> dict:
    p = home / ".cache" / "jerboa" / "market_health.ui.v1.json"
    return json.loads(p.read_text("utf-8"))

def test_dimensions_meta_exists_and_is_complete(tmp_path):
    # Run exporter (same approach used elsewhere)
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["QUIET"] = "1"

    # exporter script writes to ~/.cache/jerboa/market_health.ui.v1.json under HOME
    subprocess.run(["scripts/jerboa/bin/jerboa-market-health-ui-export"], env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    contract = _load_contract_from_cache(tmp_path)

    meta = contract.get("dimensions_meta") or contract.get("categories_meta") or {}
    assert isinstance(meta, dict)

    assert set(meta.keys()) == {"A", "B", "C", "D", "E"}

    for k in "ABCDE":
        assert isinstance(meta[k], dict)
        for field in ("display_name", "subtitle", "description"):
            assert field in meta[k]
            assert isinstance(meta[k][field], str)
            assert meta[k][field].strip() != ""

    assert meta["D"]["display_name"] == "Danger"
