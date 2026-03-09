import json
from pathlib import Path


def test_pm14_forecast_fixture_contains_selected_pair_and_candidate_pairs():
    p = Path("tests/fixtures/scenarios/forecast/jerboa_cache/recommendations.v1.json")
    assert p.exists(), "Missing forecast scenario fixture"

    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("schema") == "recommendations.v1"

    rec = data.get("recommendation") or {}
    diag = rec.get("diagnostics") or {}

    assert rec.get("action") in {"SWAP", "NOOP"}
    assert "selected_pair" in diag
    assert "candidate_pairs" in diag

    selected = diag["selected_pair"]
    assert selected["from_symbol"] == rec.get("from_symbol")
    assert selected["to_symbol"] == rec.get("to_symbol")
    assert selected["edges_by_h"] == diag.get("edges_by_h")
    assert isinstance(diag["candidate_pairs"], list)
    assert len(diag["candidate_pairs"]) >= 1
