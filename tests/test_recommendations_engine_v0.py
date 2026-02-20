from market_health.recommendations_engine import recommend


def _row(symbol: str, pts: int, checks: int = 10):
    # build minimal categories/checks structure
    # pts distributed across checks; only totals matter
    checks_list = [{"label": f"c{i}", "score": 0} for i in range(checks)]
    # assign pts as 1s then 2s deterministically
    remaining = pts
    i = 0
    while remaining > 0 and i < checks:
        add = 2 if remaining >= 2 else 1
        checks_list[i]["score"] = add
        remaining -= add
        i += 1
    return {"symbol": symbol, "categories": {"A": {"checks": checks_list}}}


def test_swap_when_delta_clears_threshold():
    # Held: XLK utility 0.40 (8/20); Candidate: XLF utility 0.70 (14/20) => delta 0.30
    scores = [_row("XLK", 8, checks=10), _row("XLF", 14, checks=10)]
    pos = {"positions": [{"symbol": "XLK"}]}
    rec = recommend(positions=pos, scores=scores, constraints={"min_improvement_threshold": 0.10, "horizon_trading_days": 5})
    assert rec.action == "SWAP"
    assert rec.from_symbol == "XLK"
    assert rec.to_symbol == "XLF"


def test_noop_when_delta_below_threshold():
    # Held: XLK 0.50 (10/20); Candidate: XLF 0.55 (11/20) => delta 0.05
    scores = [_row("XLK", 10, checks=10), _row("XLF", 11, checks=10)]
    pos = {"positions": [{"symbol": "XLK"}]}
    rec = recommend(positions=pos, scores=scores, constraints={"min_improvement_threshold": 0.10})
    assert rec.action == "NOOP"


def test_deterministic_tiebreak():
    # Two candidates equal utility; should pick alphabetical by stable tie-break
    scores = [_row("XLK", 8, checks=10), _row("XLA", 14, checks=10), _row("XLB", 14, checks=10)]
    pos = {"positions": [{"symbol": "XLK"}]}
    rec = recommend(positions=pos, scores=scores, constraints={"min_improvement_threshold": 0.10})
    assert rec.action == "SWAP"
    assert rec.to_symbol in ("XLA", "XLB")
    assert rec.to_symbol == "XLA"
