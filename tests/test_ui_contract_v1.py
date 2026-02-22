import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

VOLATILE_KEYS = {"asof", "generated_at", "updated_at", "timestamp", "ts"}


def _run_export(tmp_path: Path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)

    cmd = ["bash", "scripts/jerboa/bin/jerboa-market-health-ui-export"]
    if os.name == "nt":
        cmd = [sys.executable, "scripts/ui_export_ui_contract_v1.py"]

    subprocess.run(cmd, check=True, env=env)

    out = tmp_path / ".cache" / "jerboa" / "market_health.ui.v1.json"
    return json.loads(out.read_text(encoding="utf-8"))

def _shape_signature(d):
    def walk(x, path=""):
        out = []
        if isinstance(x, dict):
            for k in sorted(x):
                if k in VOLATILE_KEYS:
                    continue
                out += walk(x[k], f"{path}.{k}" if path else k)
        elif isinstance(x, list):
            types = sorted({type(i).__name__ for i in x})
            out.append((path, f"list[{','.join(types)}]"))
            for i in x[:1]:
                out += walk(i, f"{path}[]")
        else:
            out.append((path, type(x).__name__))
        return out

    return [f"{p}\t{t}" for p, t in walk(d)]


def _assert_envelope(contract: dict):
    assert set(contract.keys()) == {
        "schema",
        "asof",
        "status_line",
        "dimensions_meta",
        "categories_meta",
        "meta",
        "summary",
        "data",
    }
    assert contract["schema"] == "jerboa.market_health.ui.v1"
    assert isinstance(contract["status_line"], str) and contract["status_line"].strip()
    datetime.fromisoformat(contract["asof"].replace("Z", "+00:00"))
    assert isinstance(contract["meta"], dict)
    assert isinstance(contract["summary"], dict)
    assert isinstance(contract["data"], dict)


def test_contract_empty_home_is_valid(tmp_path):
    contract = _run_export(tmp_path)
    _assert_envelope(contract)

    # meta blocks exist and are well-typed
    for k in ["environment", "positions", "sectors", "state", "events_provider"]:
        m = contract["meta"][k]
        assert isinstance(m["path"], str)
        assert isinstance(m["exists"], bool)
        assert isinstance(m["bytes"], int)
        assert isinstance(m["mtime"], int)

    # optional blocks may be null when cache missing
    assert contract["data"]["environment"] is None
    assert contract["data"]["positions"] is None
    assert contract["data"]["sectors"] is None
    assert contract["data"]["state"] is None

    # events must exist and have stable shape
    ev = contract["data"]["events"]
    assert isinstance(ev, dict)
    assert isinstance(ev.get("schema"), str)
    assert isinstance(ev.get("status"), str)
    assert isinstance(ev.get("errors"), list)
    assert isinstance(ev.get("points"), list)


def test_contract_with_fixtures_is_populated_and_signature_stable(tmp_path):
    src = Path("tests/fixtures/scenarios/bullish/jerboa_cache")
    dst = tmp_path / ".cache" / "jerboa"
    (dst / "state").mkdir(parents=True, exist_ok=True)

    for f in src.glob("*.json"):
        (dst / f.name).write_text(f.read_text())
    for f in (src / "state").glob("*.json"):
        (dst / "state" / f.name).write_text(f.read_text())

    contract = _run_export(tmp_path)
    _assert_envelope(contract)

    # stable populated types (you already observed these)
    assert isinstance(contract["data"]["environment"], dict)
    assert isinstance(contract["data"]["positions"], dict)
    assert isinstance(contract["data"]["sectors"], list)
    assert isinstance(contract["data"]["state"], dict)

    expected_path = Path("tests/fixtures/expected/ui_contract.signature.tsv")
    expected = expected_path.read_text().splitlines()
    got = _shape_signature(contract)
    assert got == expected
