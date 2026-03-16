from scripts.ui_export_ui_contract_v1 import enrich_sector_rows, symbols_sample_meta


def test_enrich_sector_rows_adds_market_metadata_for_ewj() -> None:
    rows = enrich_sector_rows([{"symbol": "EWJ", "categories": {}}])

    assert rows[0]["symbol"] == "EWJ"
    assert rows[0]["market"] == "JP"
    assert rows[0]["region"] == "APAC"
    assert rows[0]["family_id"] == "broad_equity"
    assert rows[0]["benchmark_symbol"] == "TOPIX"
    assert rows[0]["calendar_id"] == "JPX"
    assert rows[0]["currency"] == "JPY"
    assert rows[0]["taxonomy"] == "topix17"


def test_symbols_sample_meta_only_returns_known_global_market_symbols() -> None:
    meta = symbols_sample_meta(["XLU", "EWJ"])

    assert len(meta) == 1
    assert meta[0]["symbol"] == "EWJ"
    assert meta[0]["market"] == "JP"
