import pytest
from market_health.policy import Scores, evaluate
from market_health.policy import constants as k


def decide(c=58, h1=63, h5=60, blend=62, owned=True, previous=0, state=""):
    return evaluate(
        Scores("TEST", c, h1, h5, blend, state),
        owned=owned,
        previous_rescue_count=previous,
        timestamp="fixed",
    )


def test_constants():
    assert (
        k.C_FLOOR,
        k.DEADBAND,
        k.BUY_BLEND_FLOOR,
        k.RESCUE_C_MIN,
        k.RESCUE_C_MAX,
        k.RESCUE_H1_EDGE,
        k.RESCUE_H5_EDGE,
    ) == (55, 3, 60, 50, 54, 10, 7)


@pytest.mark.parametrize(
    "c,h1,h5,b,owned,action",
    [
        (55, 58, 58, 60, False, "BUY"),
        (57, 73, 60, 62, False, "BUY"),
        (55, 58, 55, 60, False, "UNKNOWN"),
        (54, 70, 70, 65, False, "UNKNOWN"),
        (55, 58, 58, 59, False, "UNKNOWN"),
        (58, 61, 61, 60, False, "UNKNOWN"),
        (58, 58, 58, 58, True, "HOLD"),
        (58, 63, 58, 59, True, "HOLD"),
        (58, 63, 57, 59, True, "WATCH"),
        (58, 63, 56, 59, True, "WATCH"),
        (58, 62, 55, 57, True, "SELL"),
        (58, 55, 62, 60, True, "SELL"),
        (58, 62, 62, 55, True, "SELL"),
        (58, 62, 62, 55.01, True, "HOLD"),
        (52, 62, 59, 57, True, "HOLD — RESCUE"),
        (52, 62, 58, 57, True, "SELL"),
        (52, 61, 59, 57, True, "SELL"),
        (49, 90, 90, 90, True, "SELL"),
        (50, 60, 57, 57, True, "HOLD — RESCUE"),
        (54, 64, 61, 60, True, "HOLD — RESCUE"),
        (58, 57, 60, 60, True, "UNKNOWN"),
        (58, 58, 57, 60, True, "UNKNOWN"),
    ],
)
def test_boundaries(c, h1, h5, b, owned, action):
    d = decide(c, h1, h5, b, owned)
    assert d.action == action
    assert d.can_add == (d.buy_qualified and action in {"BUY", "HOLD"})
    assert d.timestamp == "fixed"
    assert d.reason_codes and d.human_explanation


@pytest.mark.parametrize("field", ["c", "h1", "h5", "blend"])
@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -1, 101, True, "58"])
def test_incomplete(field, bad):
    args = dict(c=58, h1=62, h5=62, blend=60)
    args[field] = bad
    d = decide(**args, previous=1)
    assert d.action == "DATA ERROR" and d.rescue_count == 1


def test_rescue_and_reset():
    assert decide(52, 65, 60, 60, previous=1).action == "SELL"
    assert decide(52, 65, 60, 60, previous=2).action == "SELL"
    assert decide(previous=1).rescue_count == 0


@pytest.mark.parametrize("state", ["DMG", "RCL", "", "OTHER"])
def test_context_does_not_override(state):
    assert decide(49, 90, 90, 90, state=state).action == "SELL"
    assert decide(58, 60, 60, 59, state=state).action == "HOLD"


def test_explanation_contains_exact_values():
    d = decide(58, 62, 53, 57)
    assert any(
        x.rule == "H5 <= C - 3" and x.actual == "53 <= 55" and x.passed
        for x in d.checks
    )


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("c", 55, True),
        ("c", 54.999, False),
        ("h1", 58, True),
        ("h1", 57.999, False),
        ("h5", 58, True),
        ("h5", 57.999, False),
        ("blend", 60, True),
        ("blend", 59.999, False),
    ],
)
def test_each_buy_gate_exact_boundary(field, value, expected):
    args = dict(c=55, h1=58, h5=58, blend=60, owned=False)
    args[field] = value
    assert decide(**args).buy_qualified is expected


@pytest.mark.parametrize("blend,expected", [(61, True), (60.999, False)])
def test_buy_blend_edge_separately(blend, expected):
    assert decide(58, 61, 61, blend, False).buy_qualified is expected


@pytest.mark.parametrize("field", ["h1", "h5", "blend"])
def test_sell_deadband_exact_and_just_above(field):
    args = dict(c=58, h1=62, h5=62, blend=60)
    args[field] = 55
    assert decide(**args).action == "SELL"
    args[field] = 55.001
    assert decide(**args).action != "SELL"


@pytest.mark.parametrize(
    "h1,h5,action",
    [
        (58, 57, "UNKNOWN"),
        (58.001, 57, "WATCH"),
        (63, 56, "WATCH"),
        (63, 55.999, "UNKNOWN"),
        (63, 58, "HOLD"),
        (58, 58, "HOLD"),
    ],
)
def test_watch_and_hold_overlap_boundaries(h1, h5, action):
    assert decide(58, h1, h5, 60).action == action
