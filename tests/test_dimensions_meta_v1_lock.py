from market_health.ui_contract_meta import DIMENSIONS_META_V1, dimensions_meta_v1


def test_dimensions_meta_v1_locked_schema():
    m = dimensions_meta_v1()
    assert m == DIMENSIONS_META_V1  # copy is exact
    assert set(m.keys()) == {"A", "B", "C", "D", "E", "F"}
    for k, v in m.items():
        assert isinstance(v, dict)
        assert set(v.keys()) == {"display_name", "description"}
        assert isinstance(v["display_name"], str) and v["display_name"].strip()
        assert isinstance(v["description"], str) and v["description"].strip()


def test_dimensions_meta_v1_stable_strings():
    # This intentionally locks the human-facing labels so they don't drift.
    assert DIMENSIONS_META_V1["A"]["display_name"] == "Narrative"
    assert DIMENSIONS_META_V1["B"]["display_name"] == "Trend"
    assert DIMENSIONS_META_V1["C"]["display_name"] == "Flow"
    assert DIMENSIONS_META_V1["D"]["display_name"] == "Risk"
    assert DIMENSIONS_META_V1["E"]["display_name"] == "Regime"
    assert DIMENSIONS_META_V1["F"]["display_name"] == "Plan"
