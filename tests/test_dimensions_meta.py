from pathlib import Path
import json
import os
import subprocess
import sys


def _load_contract_from_cache(home: Path) -> dict:
    p = home / ".cache" / "jerboa" / "market_health.ui.v1.json"
    return json.loads(p.read_text("utf-8"))


def test_dimensions_meta_exists_and_is_complete(tmp_path):
    env = os.environ.copy()
    env["QUIET"] = "1"
    env.setdefault("JERBOA_PYTHON", "python")

    # Windows: Git Bash HOME mapping; Linux: normal HOME
    if sys.platform.startswith("win"):
        env["JERBOA_HOME_WIN"] = str(tmp_path)
        home_msys = subprocess.check_output(
            ["bash", "-lc", 'cygpath -u "$JERBOA_HOME_WIN"'],
            env=env,
            text=True,
        ).strip()
        env["HOME"] = home_msys
        cmd = ["bash", "scripts/jerboa/bin/jerboa-market-health-ui-export"]
    else:
        env["HOME"] = str(tmp_path)
        cmd = ["scripts/jerboa/bin/jerboa-market-health-ui-export"]

    subprocess.run(
        cmd,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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
