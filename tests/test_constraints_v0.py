from market_health.recommendations_engine import recommend


def _row(symbol: str, score: int, sector: str | None = None) -> dict:
    row = {
        "symbol": symbol,
        "categories": {"A": {"checks": [{"label": "c", "score": score}]}},
    }
    if sector is not None:
        row["sector"] = sector
    return row


def test_max_swaps_per_day_blocks_swap():
    positions = {"schema": "positions.v1", "positions": [{"symbol": "AAA"}]}
    scores = [_row("AAA", 0), _row("BBB", 20)]
    rec = recommend(
        positions=positions,
        scores=scores,
        constraints={
            "horizon_trading_days": 5,
            "min_improvement_threshold": 0.01,
            "max_swaps_per_day": 1,
            "swaps_today": 1,
        },
    )
    assert rec.action == "NOOP"
    assert "max_swaps_per_day" in tuple(getattr(rec, "constraints_triggered", ()))


def test_sector_cap_blocks_concentration_when_sector_data_available():
    # Held: TECH + ENERGY (ENERGY is weakest). Candidate: TECH -> would raise TECH count from 1 to 2.
    positions = {
        "schema": "positions.v1",
        "positions": [{"symbol": "AAA"}, {"symbol": "CCC"}],
    }
    scores = [
        _row("AAA", 10, "TECH"),
        _row("CCC", 0, "ENERGY"),
        _row("BBB", 20, "TECH"),
    ]
    rec = recommend(
        positions=positions,
        scores=scores,
        constraints={
            "horizon_trading_days": 5,
            "min_improvement_threshold": 0.01,
            "max_swaps_per_day": 9,
            "swaps_today": 0,
            "sector_cap": 1,
        },
    )
    assert rec.action == "NOOP"
    assert "sector_cap" in tuple(getattr(rec, "constraints_triggered", ()))


def test_turnover_cap_blocks_when_too_high():
    # With 2 held symbols, turnover is 0.5 for a single swap; cap at 0.4 blocks.
    positions = {
        "schema": "positions.v1",
        "positions": [{"symbol": "AAA"}, {"symbol": "CCC"}],
    }
    scores = [_row("AAA", 10), _row("CCC", 0), _row("BBB", 20)]
    rec = recommend(
        positions=positions,
        scores=scores,
        constraints={
            "horizon_trading_days": 5,
            "min_improvement_threshold": 0.01,
            "max_swaps_per_day": 9,
            "swaps_today": 0,
            "turnover_cap": 0.4,
        },
    )
    assert rec.action == "NOOP"
    assert "turnover_cap" in tuple(getattr(rec, "constraints_triggered", ()))
