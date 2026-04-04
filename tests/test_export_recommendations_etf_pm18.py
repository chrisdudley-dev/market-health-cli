import json
import os
import subprocess
import sys
from pathlib import Path


def test_pm18_export_preserves_etf_policy_and_classification(tmp_path: Path):
    positions = {
        "schema": "positions.v1",
        "positions": [
            {"symbol": "XLB", "market_value": 100.0},
            {"symbol": "IBIT", "market_value": 900.0},
        ],
    }

    positions_p = tmp_path / "positions.json"
    out_p = tmp_path / "recommendations.json"
    positions_p.write_text(json.dumps(positions), encoding="utf-8")

    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "market_health").mkdir()
    (shim / "market_health" / "__init__.py").write_text(
        "from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )
    (shim / "market_health" / "engine.py").write_text(
        """def compute_scores(*args, **kwargs):
    def row(symbol, pts):
        checks = []
        remaining = pts
        for i in range(10):
            score = 0
            if remaining > 0:
                score = 2 if remaining >= 2 else 1
                remaining -= score
            checks.append({"label": f"c{i}", "score": score})
        return {"symbol": symbol, "categories": {"A": {"checks": checks}}}
    return [
        row("XLB", 8),
        row("IBIT", 10),
        row("BITI", 15),
        row("BITC", 14),
        row("SGOV", 7),
    ]
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["JERBOA_HOME_WIN"] = str(tmp_path)
    env["MH_ENABLE_ETF_UNIVERSE"] = "1"
    env["PYTHONPATH"] = str(shim) + os.pathsep + str(Path.cwd())

    subprocess.run(
        [
            sys.executable,
            "scripts/export_recommendations_v1.py",
            "--positions",
            str(positions_p),
            "--out",
            str(out_p),
            "--min-improvement",
            "0.12",
            "--min-floor",
            "0.55",
            "--quiet",
        ],
        check=True,
        env=env,
    )

    doc = json.loads(out_p.read_text(encoding="utf-8"))
    inputs = doc["inputs"]
    rec = doc["recommendation"]
    diag = rec["diagnostics"]
    rows = {row["sym"]: row for row in diag["candidate_rows"]}

    assert inputs["positions_mode"] == "sectorized"
    assert "IBIT" in inputs["positions_mapped"]
    assert "XLB" in inputs["positions_mapped"]
    assert inputs["positions_classified"]["ETF"] == ["IBIT"]

    assert rec["action"] == "SWAP"
    assert rec["from_symbol"] == "XLB"
    assert rec["to_symbol"] == "SGOV"
    assert diag["selection_mode"] == "sgov_fallback"
    assert diag["fallback_reason"] == "policy_blocked"

    assert "block_inverse_or_levered_etf" in rec["constraints_applied"]
    assert "block_overlap_key" in rec["constraints_applied"]

    assert "policy:block_inverse_or_levered_etf" in rows["BITI"]["rejection_reasons"]
    assert "policy:block_overlap_key" in rows["BITC"]["rejection_reasons"]
