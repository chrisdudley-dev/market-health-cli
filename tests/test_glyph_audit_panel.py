from market_health.forecast_audit import build_symbol_audit_row
from market_health.glyph_audit_panel import (
    color_display_token,
    render_glyph_audit_overview,
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


def test_color_display_token_can_render_without_color() -> None:
    assert color_display_token("699:+1+++c", color=False) == "699:+1+++c"
    assert color_display_token("BAD", color=False) == "BAD"


def test_render_glyph_audit_overview_minimal_columns_without_color() -> None:
    current = _payload_from_patterns("SYNTH", 0)
    h1 = _payload_from_patterns("SYNTH", 1)
    h5 = _payload_from_patterns("SYNTH", 2)

    row = build_symbol_audit_row(
        symbol="SYNTH",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
        is_held=True,
    )

    output = render_glyph_audit_overview([row], color=False)

    assert "Market Health — Glyph Audit Overview • GlyphSpec v1" in output
    assert "cell=totals:fingerprint   totals=C/H1/H5   •=held" in output
    assert "Sym" in output
    assert "ck" in output
    assert "SYNTH•" in output
    assert "699:+1+++c" in output
    assert "111:0f00c0" in output
    assert "866:2FuC<1" in output
    assert "955:+CC1+C" in output
    assert "566:21cFfc" in output


def test_render_glyph_audit_overview_marks_invalid_rows() -> None:
    current = _payload_from_patterns("SYNTH", 0)
    h1 = _payload_from_patterns("SYNTH", 1)
    h5 = _payload_from_patterns("SYNTH", 2)
    current["categories"]["A"]["checks"].pop()

    row = build_symbol_audit_row(
        symbol="SYNTH",
        asof="2026-05-15T14:30:00Z",
        current_payload=current,
        h1_payload=h1,
        h5_payload=h5,
    )

    output = render_glyph_audit_overview([row], color=False)

    assert "BAD" in output
    assert "FAIL" in output
