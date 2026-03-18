from scripts.export_recommendations_v1 import (
    _attach_recommendation_symbol_meta,
    _symbol_meta_dict,
)


def test_symbol_meta_dict_resolves_ewj() -> None:
    meta = _symbol_meta_dict("EWJ")

    assert meta is not None
    assert meta["symbol"] == "EWJ"
    assert meta["market"] == "JP"
    assert meta["region"] == "APAC"
    assert meta["kind"] == "broad_market"
    assert meta["family_id"] == "broad_equity"
    assert meta["benchmark_symbol"] == "TOPIX"
    assert meta["calendar_id"] == "JPX"
    assert meta["currency"] == "JPY"
    assert meta["taxonomy"] == "topix17"


def test_attach_recommendation_symbol_meta_adds_only_known_global_symbol_metadata() -> (
    None
):
    doc = {
        "schema": "recommendations.v1",
        "recommendation": {
            "action": "SWAP",
            "from_symbol": "XLU",
            "to_symbol": "EWJ",
            "diagnostics": {
                "best_candidate": "EWJ",
                "weakest_held": "XLU",
            },
        },
    }

    _attach_recommendation_symbol_meta(doc)

    rec = doc["recommendation"]
    diag = rec["diagnostics"]

    assert rec["to_symbol_meta"]["market"] == "JP"
    assert rec["to_symbol_meta"]["family_id"] == "broad_equity"
    assert diag["best_candidate_meta"]["market"] == "JP"
    assert "from_symbol_meta" not in rec
    assert "weakest_held_meta" not in diag
