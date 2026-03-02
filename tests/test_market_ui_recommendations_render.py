import json
from pathlib import Path

from market_health.market_ui import _recommendation_lines_from_contract


def test_recommendation_lines_from_contract_noop():
    rec = json.loads(
        Path(
            "tests/fixtures/scenarios/bullish/jerboa_cache/recommendations.v1.json"
        ).read_text(encoding="utf-8")
    )
    contract = {
        "summary": {"recommendations_status": "ok"},
        "data": {"recommendations": rec},
    }
    lines = _recommendation_lines_from_contract(contract)
    assert any("Recommendation:" in s for s in lines)
    assert any("NOOP" in s.upper() or "SWAP" in s.upper() for s in lines)
