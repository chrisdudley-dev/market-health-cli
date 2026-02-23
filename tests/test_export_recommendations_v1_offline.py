import json
from pathlib import Path
import subprocess
import os
import sys


def test_exporter_offline(monkeypatch, tmp_path):
    # Arrange: create a tiny positions file
    pos = {"schema": "positions.v1", "positions": [{"symbol": "XLK"}]}
    pos_p = tmp_path / "positions.v1.json"
    pos_p.write_text(json.dumps(pos), encoding="utf-8")

    # Fake compute_scores output (2 symbols: held + candidate)
    fake_rows = [
        {"symbol": "XLK", "categories": {"A": {"checks": [{"label": "c", "score": 0}]}}},
        {"symbol": "XLF", "categories": {"A": {"checks": [{"label": "c", "score": 2}]}}},
    ]

    # Monkeypatch by creating a small shim module the subprocess can import via PYTHONPATH
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "market_health").mkdir()
    (shim / "market_health" / "__init__.py").write_text(
        "from pkgutil import extend_path\n"
        "__path__ = extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )

    # Redirect market_health.engine.compute_scores
    (shim / "market_health" / "engine.py").write_text(
        "def compute_scores(*args, **kwargs):\n"
        f"    return {fake_rows!r}\n",
        encoding="utf-8",
    )

    # Use the real recommendations engine from the repo by extending sys.path order
    out_p = tmp_path / "recommendations.v1.json"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(shim) + os.pathsep + str(Path.cwd())

    # Act
    p = subprocess.run(
        [sys.executable, "scripts/export_recommendations_v1.py",
         "--positions", str(pos_p),
         "--out", str(out_p),
         "--horizon", "5",
         "--min-improvement", "0.10",
         "--quiet"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    # Assert file exists and validates with our validator script
    assert out_p.exists()
    v = subprocess.run(
        [sys.executable, "scripts/validate_recommendations_v1.py", "--path", str(out_p)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "OK: recommendations.v1 valid" in v.stdout
