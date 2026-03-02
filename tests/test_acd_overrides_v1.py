import pandas as pd

from market_health.engine import _apply_dimension_overrides


def test_apply_dimension_overrides_a_uses_latest_columns():
    df = pd.DataFrame({"a_news": [2], "a_analysts": [0]})
    checks = [{"label": "News", "score": 1}, {"label": "Analysts", "score": 1}]
    out = _apply_dimension_overrides("A", checks, df)
    assert out[0]["score"] == 2
    assert out[1]["score"] == 0


def test_apply_dimension_overrides_c_uses_latest_columns():
    df = pd.DataFrame({"c_money_flow": [3]})
    checks = [{"label": "Money Flow", "score": 0}]
    out = _apply_dimension_overrides("C", checks, df)
    assert out[0]["score"] == 3


def test_apply_dimension_overrides_d_uses_latest_columns():
    df = pd.DataFrame({"d_iv_pct": [4]})
    checks = [{"label": "IV%", "score": 1}]
    out = _apply_dimension_overrides("D", checks, df)
    assert out[0]["score"] == 4
