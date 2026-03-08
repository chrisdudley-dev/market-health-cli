from market_health.recommendations_engine import recommend


def _row(symbol: str, pts: int, checks: int = 10, **extra):
    checks_list = [{"label": f"c{i}", "score": 0} for i in range(checks)]
    remaining = pts
    i = 0
    while remaining > 0 and i < checks:
        add = 2 if remaining >= 2 else 1
        checks_list[i]["score"] = add
        remaining -= add
        i += 1
    row = {"symbol": symbol, "categories": {"A": {"checks": checks_list}}}
    row.update(extra)
    return row


def test_precious_candidate_can_win_replacement():
    scores = [
        _row("XLB", 8, asset_type="sector", group="SECTOR"),
        _row("XLE", 11, asset_type="sector", group="SECTOR"),
        _row(
            "GLDM",
            14,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="gold",
            is_basket=False,
        ),
        _row("SGOV", 7, asset_type="parking", group="PARKING"),
    ]
    pos = {"positions": [{"symbol": "XLB"}]}

    rec = recommend(
        positions=pos,
        scores=scores,
        constraints={
            "min_floor": 0.55,
            "min_delta": 0.12,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": True,
        },
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "XLB"
    assert rec.to_symbol == "GLDM"
    assert rec.diagnostics["selection_mode"] == "best_candidate"


def test_sgov_fallback_when_no_candidate_clears_floor_and_delta():
    scores = [
        _row("XLK", 10, asset_type="sector", group="SECTOR"),
        _row("XLF", 11, asset_type="sector", group="SECTOR"),
        _row(
            "GLDM",
            10,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="gold",
            is_basket=False,
        ),
        _row("SGOV", 8, asset_type="parking", group="PARKING"),
    ]
    pos = {"positions": [{"symbol": "XLK"}]}

    rec = recommend(
        positions=pos,
        scores=scores,
        constraints={
            "min_floor": 0.55,
            "min_delta": 0.12,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": True,
        },
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "XLK"
    assert rec.to_symbol == "SGOV"
    assert rec.diagnostics["selection_mode"] == "policy_fallback"
    assert rec.diagnostics["fallback_reason"] == "no_candidate_clears_floor_and_delta"


def test_candidate_rejection_reasons_include_floor_and_delta():
    scores = [
        _row("XLP", 10, asset_type="sector", group="SECTOR"),
        _row("XLF", 11, asset_type="sector", group="SECTOR"),
        _row(
            "GLDM",
            10,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="gold",
            is_basket=False,
        ),
    ]
    pos = {"positions": [{"symbol": "XLP"}]}

    rec = recommend(
        positions=pos,
        scores=scores,
        constraints={
            "min_floor": 0.55,
            "min_delta": 0.12,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": False,
        },
    )

    assert rec.action == "NOOP"

    rows = {row["sym"]: row for row in rec.diagnostics["candidate_rows"]}
    assert "below_delta" in rows["XLF"]["rejection_reasons"]
    assert "below_floor" in rows["GLDM"]["rejection_reasons"]
    assert "below_delta" in rows["GLDM"]["rejection_reasons"]


def test_constraint_failure_is_exposed_on_selected_candidate():
    scores = [
        _row("XLB", 8, asset_type="sector", group="SECTOR"),
        _row(
            "GLDM",
            14,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="gold",
            is_basket=False,
        ),
        _row("SGOV", 7, asset_type="parking", group="PARKING"),
    ]
    pos = {"positions": [{"symbol": "XLB"}]}

    rec = recommend(
        positions=pos,
        scores=scores,
        constraints={
            "min_floor": 0.55,
            "min_delta": 0.12,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": True,
            "max_swaps_per_day": 1,
            "swaps_today": 1,
        },
    )

    assert rec.action == "NOOP"
    assert "max_swaps_per_day" in rec.constraints_triggered

    rows = {row["sym"]: row for row in rec.diagnostics["candidate_rows"]}
    assert "constraint:max_swaps_per_day" in rows["GLDM"]["rejection_reasons"]
