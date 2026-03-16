from market_health.engine import get_symbol_market_context, is_known_non_us_symbol


def test_engine_resolves_japan_market_metadata_for_ewj() -> None:
    ctx = get_symbol_market_context("EWJ")

    assert ctx is not None
    assert ctx["symbol"] == "EWJ"
    assert ctx["market"] == "JP"
    assert ctx["region"] == "APAC"
    assert ctx["kind"] == "broad_market"
    assert ctx["family_id"] == "broad_equity"
    assert ctx["benchmark_symbol"] == "TOPIX"
    assert ctx["calendar_id"] == "JPX"
    assert ctx["currency"] == "JPY"
    assert ctx["taxonomy"] == "topix17"
    assert ctx["session_model"] == "cash_equity"

    assert is_known_non_us_symbol("EWJ") is True
    assert is_known_non_us_symbol("XLE") is False
