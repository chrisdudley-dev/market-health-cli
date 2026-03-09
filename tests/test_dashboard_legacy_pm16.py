import json
from pathlib import Path

from market_health.dashboard_legacy import render_reco


def test_pm16_dashboard_prefers_selected_pair_for_forecast_swap():
    rec_doc = json.loads(
        Path(
            "tests/fixtures/scenarios/forecast/jerboa_cache/recommendations.v1.json"
        ).read_text(encoding="utf-8")
    )

    text = render_reco([], {}, rec_doc, ["AAA", "BBB"])

    assert "BBB" in text
    assert "DDD" in text
    assert "portfolio_weighted_robust_edge" in text
