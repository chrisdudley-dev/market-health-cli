from pathlib import Path
import json
import os
import subprocess


def _load_contract_from_cache(home):
    p = home / ".cache" / "jerboa" / "market_health.ui.v1.json"
    if p.exists():
        return json.loads(p.read_text("utf-8"))

    # Windows + Git Bash can map HOME to MSYS paths, so read via bash in the same HOME.
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.setdefault("JERBOA_PYTHON", "python")

    txt = subprocess.check_output(
        ["bash", "-lc", 'cat "$HOME/.cache/jerboa/market_health.ui.v1.json"'],
        env=env,
        text=True,
    )
    return json.loads(txt)

def test_dimensions_meta_exists_and_is_complete(tmp_path):
    # Run exporter (same approach used elsewhere)
    env = os.environ.copy()
    env["JERBOA_HOME_WIN"] = str(tmp_path)
    # Make HOME MSYS-friendly for bash, while Python writes to JERBOA_HOME_WIN
    home_msys = subprocess.check_output(
        ["bash", "-lc", 'cygpath -u "$JERBOA_HOME_WIN"'],
        env=env,
        text=True,
    ).strip()
    env["HOME"] = home_msys
    env["QUIET"] = "1"
    env["JERBOA_PYTHON"] = "python"

    # exporter script writes to ~/.cache/jerboa/market_health.ui.v1.json under HOME
    subprocess.run(
        ["bash", "scripts/jerboa/bin/jerboa-market-health-ui-export"],
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
