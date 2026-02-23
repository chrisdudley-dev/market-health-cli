import json
import re
from pathlib import Path


def test_bullish_recommendations_fixture_is_valid_schema():
    p = Path("tests/fixtures/scenarios/bullish/jerboa_cache/recommendations.v1.json")
    data = json.loads(p.read_text(encoding="utf-8"))

    assert isinstance(data, dict)
    assert data.get("schema") == "recommendations.v1"
    assert isinstance(data.get("asof"), str)
    assert isinstance(data.get("generated_at"), str)
    assert isinstance(data.get("inputs"), dict)

    rec = data.get("recommendation")
    assert isinstance(rec, dict)

    assert isinstance(rec.get("horizon_trading_days"), int)
    assert isinstance(rec.get("target_trade_date"), str)
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", rec["target_trade_date"])

    assert isinstance(rec.get("action"), str)
    assert isinstance(rec.get("constraints_applied"), list)
    assert isinstance(rec.get("diagnostics"), dict)
