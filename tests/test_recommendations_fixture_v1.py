import json
from pathlib import Path


def test_bullish_recommendations_fixture_is_valid_schema():
    p = Path("tests/fixtures/scenarios/bullish/jerboa_cache/recommendations.v1.json")
    data = json.loads(p.read_text(encoding="utf-8"))

    assert isinstance(data, dict)
    assert data.get("schema") == "recommendations.v1"

    # Stable top-level metadata
    assert "asof" in data and isinstance(data["asof"], str)
    assert "generated_at" in data and isinstance(data["generated_at"], str)

    # Inputs block exists and is a dict
    assert "inputs" in data and isinstance(data["inputs"], dict)

    # Current schema uses singular "recommendation"
    assert "recommendation" in data and isinstance(data["recommendation"], dict)
    rec = data["recommendation"]

    # Stable core fields
    assert "action" in rec and isinstance(rec["action"], str)
    assert "constraints_applied" in rec and isinstance(rec["constraints_applied"], list)

    # Diagnostics contain held_scored list (as seen in fixture)
    assert "diagnostics" in rec and isinstance(rec["diagnostics"], dict)
    assert "held_scored" in rec["diagnostics"]
    assert isinstance(rec["diagnostics"]["held_scored"], list)
