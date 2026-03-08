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


def _candidate_rows(rec):
    rows = rec.diagnostics["candidate_rows"]
    return {row["sym"]: row for row in rows}


def test_second_precious_holding_is_blocked_and_falls_back_to_sgov():
    scores = [
        _row("XLB", 8, asset_type="sector", group="SECTOR"),
        _row(
            "PALL",
            13,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="palladium",
            is_basket=False,
        ),
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
    pos = {"positions": [{"symbol": "XLB"}, {"symbol": "PALL"}]}

    rec = recommend(
        positions=pos,
        scores=scores,
        constraints={
            "min_floor": 0.55,
            "min_delta": 0.12,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": True,
            "max_precious_holdings": 1,
            "block_gltr_component_overlap": True,
        },
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "XLB"
    assert rec.to_symbol == "SGOV"
    assert rec.diagnostics["selection_mode"] == "sgov_fallback"

    rows = _candidate_rows(rec)
    assert "policy:max_precious_holdings" in rows["GLDM"]["rejection_reasons"]


def test_gltr_overlap_is_blocked_and_falls_back_to_sgov():
    scores = [
        _row("XLB", 8, asset_type="sector", group="SECTOR"),
        _row(
            "PALL",
            13,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="palladium",
            is_basket=False,
        ),
        _row(
            "GLTR",
            14,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="basket",
            is_basket=True,
        ),
        _row("SGOV", 7, asset_type="parking", group="PARKING"),
    ]
    pos = {"positions": [{"symbol": "XLB"}, {"symbol": "PALL"}]}

    rec = recommend(
        positions=pos,
        scores=scores,
        constraints={
            "min_floor": 0.55,
            "min_delta": 0.12,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": True,
            "max_precious_holdings": 2,
            "block_gltr_component_overlap": True,
        },
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "XLB"
    assert rec.to_symbol == "SGOV"
    assert rec.diagnostics["selection_mode"] == "sgov_fallback"

    rows = _candidate_rows(rec)
    assert "policy:block_gltr_component_overlap" in rows["GLTR"]["rejection_reasons"]


def test_precious_replacement_is_allowed_when_replacing_existing_precious():
    scores = [
        _row(
            "GLDM",
            8,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="gold",
            is_basket=False,
        ),
        _row(
            "PALL",
            14,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="palladium",
            is_basket=False,
        ),
        _row("SGOV", 7, asset_type="parking", group="PARKING"),
    ]
    pos = {"positions": [{"symbol": "GLDM"}]}

    rec = recommend(
        positions=pos,
        scores=scores,
        constraints={
            "min_floor": 0.55,
            "min_delta": 0.12,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": True,
            "max_precious_holdings": 1,
            "block_gltr_component_overlap": True,
        },
    )

    assert rec.action == "SWAP"
    assert rec.from_symbol == "GLDM"
    assert rec.to_symbol == "PALL"
    assert rec.diagnostics["selection_mode"] == "best_candidate"
