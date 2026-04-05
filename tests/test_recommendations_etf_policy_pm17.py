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
    return {row["sym"]: row for row in rec.diagnostics["candidate_rows"]}


def test_inverse_or_levered_etf_is_blocked_by_policy(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")

    scores = [
        _row("XLB", 8, asset_type="sector", group="SECTOR"),
        _row("BITI", 14),
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
    assert rec.to_symbol == "SGOV"
    rows = _candidate_rows(rec)
    assert "policy:block_inverse_or_levered_etf" in rows["BITI"]["rejection_reasons"]


def test_overlap_key_blocks_duplicate_etf_exposure(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")

    scores = [
        _row("XLB", 8, asset_type="sector", group="SECTOR"),
        _row("IBIT", 12),
        _row("BITC", 14),
        _row("SGOV", 7, asset_type="parking", group="PARKING"),
    ]
    pos = {"positions": [{"symbol": "XLB"}, {"symbol": "IBIT"}]}

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
    assert rec.to_symbol == "SGOV"
    rows = _candidate_rows(rec)
    assert "policy:block_overlap_key" in rows["BITC"]["rejection_reasons"]


def test_overlap_key_does_not_block_when_replacing_same_exposure(monkeypatch):
    monkeypatch.setenv("MH_ENABLE_ETF_UNIVERSE", "1")

    scores = [
        _row("IBIT", 8),
        _row("BITC", 14),
        _row("SGOV", 7, asset_type="parking", group="PARKING"),
    ]
    pos = {"positions": [{"symbol": "IBIT"}]}

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
    assert rec.from_symbol == "IBIT"
    assert rec.to_symbol == "BITC"
