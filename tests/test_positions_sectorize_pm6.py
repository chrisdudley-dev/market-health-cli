from market_health.positions_sectorize import sectorize_positions


def test_sectorize_positions_classifies_supported_non_sector_holdings():
    positions = {
        "schema": "positions.v1",
        "positions": [
            {"symbol": "GLDM", "market_value": 100.0},
            {"symbol": "SGOV", "market_value": 50.0},
            {"symbol": "XLE", "market_value": 75.0},
            {"symbol": "ZZZZ", "market_value": 10.0},
        ],
    }

    out, meta = sectorize_positions(positions, {"XLE"})

    assert out["positions"] == [{"symbol": "XLE", "market_value": 75.0}]
    assert meta["mapped"] == ["XLE"]
    assert meta["supported_outside_universe"] == ["GLDM", "SGOV"]
    assert meta["unmapped"] == ["ZZZZ"]
    assert meta["classified"]["PRECIOUS"] == ["GLDM"]
    assert meta["classified"]["PARKING"] == ["SGOV"]
    assert meta["classified"]["SECTOR"] == ["XLE"]
    assert meta["classified"]["UNSUPPORTED"] == ["ZZZZ"]


def test_sectorize_positions_maps_precious_when_in_universe():
    positions = {
        "schema": "positions.v1",
        "positions": [{"symbol": "GLDM", "market_value": 125.0}],
    }

    out, meta = sectorize_positions(positions, {"GLDM", "SGOV"})

    assert out["positions"] == [{"symbol": "GLDM", "market_value": 125.0}]
    assert meta["mapped"] == ["GLDM"]
    assert meta["supported_outside_universe"] == []
    assert meta["unmapped"] == []
    assert meta["classified"]["PRECIOUS"] == ["GLDM"]


def test_sectorize_positions_maps_enabled_etf_holdings_when_in_universe(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")
    positions = {
        "schema": "positions.v1",
        "positions": [
            {"symbol": "IBIT", "market_value": 1000.0},
            {"symbol": "ETHA", "market_value": 500.0},
        ],
    }

    out, meta = sectorize_positions(positions, {"XLE", "IBIT", "ETHA"})

    assert out["positions"] == [
        {"symbol": "ETHA", "market_value": 500.0},
        {"symbol": "IBIT", "market_value": 1000.0},
    ]
    assert meta["mapped"] == ["ETHA", "IBIT"]
    assert meta["supported_outside_universe"] == []
    assert meta["unmapped"] == []
    assert meta["classified"]["ETF"] == ["ETHA", "IBIT"]


def test_sectorize_positions_marks_enabled_etf_holdings_supported_outside_universe(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")
    positions = {
        "schema": "positions.v1",
        "positions": [{"symbol": "IBIT", "market_value": 1000.0}],
    }

    out, meta = sectorize_positions(positions, {"XLE"})

    assert out["positions"] == []
    assert meta["mapped"] == []
    assert meta["supported_outside_universe"] == ["IBIT"]
    assert meta["unmapped"] == []
    assert meta["classified"]["ETF"] == ["IBIT"]
