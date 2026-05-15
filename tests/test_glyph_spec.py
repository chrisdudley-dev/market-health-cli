import pytest

from market_health.glyph_spec import (
    GLYPH_SPEC_VERSION,
    PATTERN_TO_GLYPH,
    all_glyph_patterns,
    base13_to_int,
    decode_fingerprint,
    decode_glyph,
    decode_totals,
    display_category_token,
    encode_fingerprint,
    encode_pattern,
    encode_totals,
    int_to_base13,
    make_category_token,
    row_checksum,
    totals_from_patterns,
    validate_category_token,
)


def test_glyph_spec_version_is_v1() -> None:
    assert GLYPH_SPEC_VERSION == "GlyphSpec v1"


def test_glyph_map_is_frozen() -> None:
    assert PATTERN_TO_GLYPH == {
        "000": "0",
        "111": "1",
        "222": "2",
        "100": "c",
        "200": "C",
        "010": "h",
        "020": "H",
        "001": "w",
        "002": "W",
        "110": "n",
        "220": "N",
        "101": "u",
        "202": "U",
        "011": "f",
        "022": "F",
        "012": ">",
        "210": "<",
        "102": "r",
        "201": "d",
        "021": "p",
        "120": "s",
        "112": "/",
        "221": "\\",
        "121": "^",
        "212": "V",
        "122": "+",
        "211": "-",
    }


def test_all_27_patterns_round_trip() -> None:
    patterns = all_glyph_patterns()

    assert len(patterns) == 27
    assert set(patterns) == set(PATTERN_TO_GLYPH)

    for pattern in patterns:
        glyph = encode_pattern(pattern)
        assert decode_glyph(glyph) == pattern


def test_base13_totals_round_trip() -> None:
    for value, digit in enumerate("0123456789ABC"):
        assert int_to_base13(value) == digit
        assert base13_to_int(digit) == value

    assert encode_totals((6, 10, 12)) == "6AC"
    assert decode_totals("6AC") == (6, 10, 12)


def test_example_token_validates() -> None:
    validation = validate_category_token("A=668:0Hr/V2")

    assert validation.valid
    assert validation.category == "A"
    assert validation.totals == (6, 6, 8)
    assert validation.decoded_totals == (6, 6, 8)
    assert validation.patterns == ("000", "020", "102", "112", "212", "222")
    assert display_category_token("A=668:0Hr/V2") == "668:0Hr/V2"


def test_make_category_token_from_patterns() -> None:
    token = make_category_token(
        "A",
        ["000", "020", "102", "112", "212", "222"],
    )

    assert token == "A=668:0Hr/V2"
    assert validate_category_token(token).valid


def test_corrupted_visible_total_fails_validation() -> None:
    validation = validate_category_token("A=6A7:0Hr/V2")

    assert not validation.valid
    assert validation.totals == (6, 10, 7)
    assert validation.decoded_totals == (6, 6, 8)
    assert validation.error == "visible totals do not match decoded fingerprint totals"


def test_unknown_glyph_fails_validation() -> None:
    validation = validate_category_token("A=668:0Hr?V2")

    assert not validation.valid
    assert validation.error == "unknown GlyphSpec v1 glyph: '?'"


@pytest.mark.parametrize(
    "token",
    [
        "A=668:0Hr/V",
        "A=668:0Hr/V22",
        "Z=668:0Hr/V2",
        "A=66:0Hr/V2",
        "A=6680Hr/V2",
    ],
)
def test_malformed_tokens_fail_validation(token: str) -> None:
    assert not validate_category_token(token).valid


def test_fingerprint_totals_and_round_trip() -> None:
    patterns = ("122", "111", "122", "122", "122", "100")

    assert encode_fingerprint(patterns) == "+1+++c"
    assert decode_fingerprint("+1+++c") == patterns
    assert totals_from_patterns(patterns) == (6, 9, 9)


def test_row_checksum_is_stable_and_detects_changes() -> None:
    tokens = {
        "A": "A=699:+1+++c",
        "B": "B=111:0f00c0",
        "C": "C=866:2FuC<1",
        "D": "D=955:+CC1+C",
        "E": "E=566:21cFfc",
    }

    checksum = row_checksum(
        symbol="SYNTH",
        asof="2026-05-15T14:30:00Z",
        category_tokens=tokens,
    )

    assert checksum == row_checksum(
        symbol="synth",
        asof="2026-05-15T14:30:00Z",
        category_tokens=tokens,
    )

    changed = dict(tokens)
    changed["E"] = "E=567:21cFf/"
    assert checksum != row_checksum(
        symbol="SYNTH",
        asof="2026-05-15T14:30:00Z",
        category_tokens=changed,
    )


def test_invalid_inputs_raise_for_encoder_helpers() -> None:
    with pytest.raises(ValueError):
        encode_pattern("123")

    with pytest.raises(ValueError):
        make_category_token("Z", ["000"] * 6)

    with pytest.raises(ValueError):
        encode_fingerprint(["000"] * 5)

    with pytest.raises(ValueError):
        row_checksum(
            symbol="SYNTH",
            asof="2026-05-15T14:30:00Z",
            category_tokens=[],
            length=1,
        )
