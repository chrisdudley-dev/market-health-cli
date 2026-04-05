import json
from pathlib import Path


def test_pm18_etf_policy_fixture_captures_etf_inputs_and_policy_blocks():
    p = Path("tests/fixtures/scenarios/etf_policy/jerboa_cache/recommendations.v1.json")
    assert p.exists(), "Missing ETF policy scenario fixture"

    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("schema") == "recommendations.v1"

    inputs = data.get("inputs") or {}
    classified = inputs.get("positions_classified") or {}

    assert inputs.get("positions_mode") == "sectorized"
    assert "IBIT" in (inputs.get("positions_mapped") or [])
    assert "XLB" in (inputs.get("positions_mapped") or [])
    assert classified.get("ETF") == ["IBIT"]

    rec = data.get("recommendation") or {}
    diag = rec.get("diagnostics") or {}
    rows = {row["sym"]: row for row in diag.get("candidate_rows") or []}

    assert rec.get("action") == "SWAP"
    assert rec.get("from_symbol") == "XLB"
    assert rec.get("to_symbol") == "SGOV"
    assert diag.get("selection_mode") == "sgov_fallback"
    assert diag.get("fallback_reason") == "policy_blocked"

    assert "block_inverse_or_levered_etf" in (rec.get("constraints_applied") or [])
    assert "block_overlap_key" in (rec.get("constraints_applied") or [])

    assert "BITI" in rows
    assert "BITC" in rows
    assert "SGOV" in rows

    assert "policy:block_inverse_or_levered_etf" in rows["BITI"]["rejection_reasons"]
    assert "policy:block_overlap_key" in rows["BITC"]["rejection_reasons"]
