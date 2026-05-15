import json

from market_health.forecast_audit import (
    build_category_audit_cell,
    build_symbol_audit_row,
    category_patterns_from_payloads,
    forecast_audit_document,
    symbol_audit_row_to_dict,
    write_forecast_audit_json,
)


PATTERNS_BY_CATEGORY = {
    "A": ["122", "111", "122", "122", "122", "100"],
    "B": ["000", "011", "000", "000", "100", "000"],
    "C": ["222", "022", "101", "200", "210", "111"],
    "D": ["122", "200", "200", "111", "122", "200"],
    "E": ["222", "111", "100", "022", "011", "100"],
}


def _payload_from_patterns(symbol: str, horizon_index: int) -> dict:
    categories = {}
    for category, patterns in PATTERNS_BY_CATEGORY.items():
        categories[category] = {
            "checks": [
                {"id": f"{category}{index + 1}", "score": int(pattern[horizon_index])}
                for index, pattern in enumerate(patterns)
            ]
        }

    return {"symbol": symbol, "categories": categories}


def test_category_patterns_are_built_from_current_h1_h5_payloads() -> None:
    current = _payload_from_patterns("SYNTH", 0)
    h1 = _payload_from_patterns("SYNTH", 1)
    h5 = _payload_from_patterns("SYNTH", 2)

    assert category_patterns_from_payloads(
        category="A",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    ) == tuple(PATTERNS_BY_CATEGORY["A"])


def test_build_category_audit_cell_produces_canonical_and_display_tokens() -> None:
    current = _payload_from_patterns("SYNTH", 0)
    h1 = _payload_from_patterns("SYNTH", 1)
    h5 = _payload_from_patterns("SYNTH", 2)

    cell = build_category_audit_cell(
        category="A",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    )

    assert cell.valid
    assert cell.category == "A"
    assert cell.token == "A=699:+1+++c"
    assert cell.display_token == "699:+1+++c"
    assert cell.totals == (6, 9, 9)
    assert cell.fingerprint == "+1+++c"
    assert cell.patterns == tuple(PATTERNS_BY_CATEGORY["A"])


def test_build_symbol_audit_row_contains_all_category_cells() -> None:
    current = _payload_from_patterns("synth", 0)
    h1 = _payload_from_patterns("synth", 1)
    h5 = _payload_from_patterns("synth", 2)

    row = build_symbol_audit_row(
        symbol="synth",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
        is_held=True,
    )

    assert row.symbol == "SYNTH"
    assert row.asof == "2026-05-15T14:30:00Z"
    assert row.is_held
    assert row.all_valid
    assert len(row.checksum) == 4

    assert row.canonical_tokens == {
        "A": "A=699:+1+++c",
        "B": "B=111:0f00c0",
        "C": "C=866:2FuC<1",
        "D": "D=955:+CC1+C",
        "E": "E=566:21cFfc",
    }

    assert row.display_cells == {
        "A": "699:+1+++c",
        "B": "111:0f00c0",
        "C": "866:2FuC<1",
        "D": "955:+CC1+C",
        "E": "566:21cFfc",
    }


def test_row_checksum_changes_when_payload_changes() -> None:
    current = _payload_from_patterns("SYNTH", 0)
    h1 = _payload_from_patterns("SYNTH", 1)
    h5 = _payload_from_patterns("SYNTH", 2)

    original = build_symbol_audit_row(
        symbol="SYNTH",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    )

    changed_h5 = _payload_from_patterns("SYNTH", 2)
    changed_h5["categories"]["E"]["checks"][5]["score"] = 2

    changed = build_symbol_audit_row(
        symbol="SYNTH",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=changed_h5,
    )

    assert original.checksum != changed.checksum


def test_invalid_category_payload_marks_cell_bad_without_crashing() -> None:
    current = _payload_from_patterns("SYNTH", 0)
    h1 = _payload_from_patterns("SYNTH", 1)
    h5 = _payload_from_patterns("SYNTH", 2)
    current["categories"]["A"]["checks"].pop()

    cell = build_category_audit_cell(
        category="A",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    )

    assert not cell.valid
    assert cell.display_token == "BAD"
    assert cell.error == "category A must contain exactly six checks"


def test_invalid_cell_makes_symbol_row_invalid_but_still_checksumed() -> None:
    current = _payload_from_patterns("SYNTH", 0)
    h1 = _payload_from_patterns("SYNTH", 1)
    h5 = _payload_from_patterns("SYNTH", 2)
    current["categories"]["C"]["checks"][0]["score"] = 9

    row = build_symbol_audit_row(
        symbol="SYNTH",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    )

    assert not row.all_valid
    assert row.cells["C"].display_token == "BAD"
    assert row.cells["C"].error == "category C check 1 score must be 0, 1, or 2"
    assert len(row.checksum) == 4


def test_symbol_audit_row_serializes_for_export() -> None:
    current = _payload_from_patterns("synth", 0)
    h1 = _payload_from_patterns("synth", 1)
    h5 = _payload_from_patterns("synth", 2)

    row = build_symbol_audit_row(
        symbol="synth",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
        is_held=True,
    )

    exported = symbol_audit_row_to_dict(row)

    assert exported["symbol"] == "SYNTH"
    assert exported["is_held"] is True
    assert exported["valid"] is True
    assert exported["cells"]["A"]["token"] == "A=699:+1+++c"
    assert exported["cells"]["A"]["display_token"] == "699:+1+++c"
    assert exported["cells"]["A"]["totals"] == [6, 9, 9]
    assert exported["display_cells"]["A"] == "699:+1+++c"
    assert exported["canonical_tokens"]["A"] == "A=699:+1+++c"


def test_forecast_audit_document_has_stable_v1_shape() -> None:
    current = _payload_from_patterns("synth", 0)
    h1 = _payload_from_patterns("synth", 1)
    h5 = _payload_from_patterns("synth", 2)

    row = build_symbol_audit_row(
        symbol="synth",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    )

    doc = forecast_audit_document([row], asof="2026-05-15T14:30:00Z")

    assert doc["schema"] == "forecast_audit.v1"
    assert doc["glyph_spec_version"] == "GlyphSpec v1"
    assert doc["asof"] == "2026-05-15T14:30:00Z"
    assert doc["columns"] == ["Sym", "A", "B", "C", "D", "E", "ck"]
    assert doc["row_count"] == 1
    assert doc["rows"][0]["symbol"] == "SYNTH"


def test_write_forecast_audit_json_round_trips(tmp_path) -> None:
    current = _payload_from_patterns("synth", 0)
    h1 = _payload_from_patterns("synth", 1)
    h5 = _payload_from_patterns("synth", 2)

    row = build_symbol_audit_row(
        symbol="synth",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    )

    out = write_forecast_audit_json(
        tmp_path / "forecast_audit.v1.json",
        [row],
        asof="2026-05-15T14:30:00Z",
    )

    loaded = json.loads(out.read_text(encoding="utf-8"))

    assert loaded["schema"] == "forecast_audit.v1"
    assert loaded["row_count"] == 1
    assert loaded["rows"][0]["cells"]["A"]["token"] == "A=699:+1+++c"
