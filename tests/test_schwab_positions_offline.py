import json
import os
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "docs" / "examples" / "schwab_accounts.sample.json"


def _run(cmd):
    r = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
    )
    if r.returncode != 0:
        raise AssertionError(
            "Command failed:\n"
            f"  rc={r.returncode}\n"
            f"  cmd={' '.join(map(str, cmd))}\n"
            f"--- STDOUT ---\n{r.stdout}\n"
            f"--- STDERR ---\n{r.stderr}\n"
        )
    return (r.stdout or "") + (r.stderr or "")


def test_offline_importer_produces_valid_positions_v1(tmp_path):
    import pytest

    if not SAMPLE.exists():
        pytest.skip(f"missing sample fixture: {SAMPLE}")

    out = tmp_path / "positions.v1.json"

    _run(
        [
            sys.executable,
            "scripts/import_positions_schwab_json.py",
            "--in",
            str(SAMPLE),
            "--out",
            str(out),
        ]
    )

    out_text = _run(
        [sys.executable, "scripts/validate_positions_v1.py", "--path", str(out)]
    )
    assert "OK: positions.v1 valid" in out_text

    doc = json.loads(out.read_text("utf-8"))
    assert doc.get("schema") == "positions.v1"
    positions = doc.get("positions")
    assert isinstance(positions, list)
    assert len(positions) >= 1

    syms = {p.get("symbol") for p in positions if isinstance(p, dict)}
    assert "AAPL" in syms


def test_refresh_positions_cache_supports_schwab_json(tmp_path):
    import pytest

    if os.name != "posix":
        pytest.skip("bash-based refresh script requires POSIX")
    if not SAMPLE.exists():
        pytest.skip(f"missing sample fixture: {SAMPLE}")

    out = tmp_path / "positions.v1.json"

    _run(
        [
            "bash",
            "scripts/cache/refresh_positions_cache.sh",
            "--schwab-json",
            str(SAMPLE),
            "--out",
            str(out),
        ]
    )

    out_text = _run(
        [sys.executable, "scripts/validate_positions_v1.py", "--path", str(out)]
    )
    assert "OK: positions.v1 valid" in out_text
