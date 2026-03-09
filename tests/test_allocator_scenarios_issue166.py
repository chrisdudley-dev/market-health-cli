import json
from pathlib import Path

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


def _expand_score_rows(rows):
    expanded = []
    for row in rows:
        row = dict(row)
        pts = int(row.pop("pts"))
        expanded.append(_row(pts=pts, **row))
    return expanded


def test_issue166_allocator_scenarios():
    p = Path("tests/fixtures/allocator_scenarios_issue166.v1.json")
    doc = json.loads(p.read_text(encoding="utf-8"))

    assert doc["schema"] == "allocator_scenarios_issue166.v1"

    for sc in doc["scenarios"]:
        rec = recommend(
            positions=sc["positions"],
            scores=_expand_score_rows(sc["score_rows"]),
            constraints=sc["constraints"],
        )

        exp = sc["expected"]
        assert rec.action == exp["action"], sc["name"]
        assert rec.from_symbol == exp.get("from_symbol"), sc["name"]
        assert rec.to_symbol == exp.get("to_symbol"), sc["name"]

        diag = rec.diagnostics or {}
        if "selection_mode" in exp:
            assert diag.get("selection_mode") == exp["selection_mode"], sc["name"]
        if "fallback_reason" in exp:
            assert diag.get("fallback_reason") == exp["fallback_reason"], sc["name"]

        reasons_by_symbol = exp.get("rejection_reasons_by_symbol") or {}
        if reasons_by_symbol:
            rows = {row["sym"]: row for row in diag.get("candidate_rows", [])}
            for sym, reasons in reasons_by_symbol.items():
                got = rows[sym]["rejection_reasons"]
                for reason in reasons:
                    assert reason in got, f"{sc['name']} {sym} missing {reason}"
