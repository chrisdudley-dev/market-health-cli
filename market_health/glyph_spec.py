from __future__ import annotations

import itertools
import re
import zlib
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

GLYPH_SPEC_VERSION = "GlyphSpec v1"

CATEGORY_KEYS = ("A", "B", "C", "D", "E")
BASE13_DIGITS = "0123456789ABC"

PATTERN_TO_GLYPH: dict[str, str] = {
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

GLYPH_TO_PATTERN: dict[str, str] = {
    glyph: pattern for pattern, glyph in PATTERN_TO_GLYPH.items()
}

_CATEGORY_TOKEN_RE = re.compile(r"^([A-E])=([0-9ABC]{3}):(.{6})$")


@dataclass(frozen=True)
class CategoryTokenValidation:
    category: str | None
    token: str
    valid: bool
    totals: tuple[int, int, int] | None = None
    decoded_totals: tuple[int, int, int] | None = None
    fingerprint: str | None = None
    patterns: tuple[str, ...] = ()
    error: str | None = None


def _normalize_pattern(pattern: Sequence[int | str] | str) -> str:
    if isinstance(pattern, str):
        text = pattern.strip()
    else:
        text = "".join(str(x) for x in pattern)

    if len(text) != 3 or any(ch not in "012" for ch in text):
        raise ValueError(f"invalid glyph pattern: {pattern!r}")

    return text


def encode_pattern(pattern: Sequence[int | str] | str) -> str:
    text = _normalize_pattern(pattern)
    return PATTERN_TO_GLYPH[text]


def decode_glyph(glyph: str) -> str:
    if len(glyph) != 1 or glyph not in GLYPH_TO_PATTERN:
        raise ValueError(f"unknown GlyphSpec v1 glyph: {glyph!r}")
    return GLYPH_TO_PATTERN[glyph]


def int_to_base13(value: int) -> str:
    if not isinstance(value, int) or value < 0 or value > 12:
        raise ValueError(f"category total must be 0..12: {value!r}")
    return BASE13_DIGITS[value]


def base13_to_int(value: str) -> int:
    if len(value) != 1 or value not in BASE13_DIGITS:
        raise ValueError(f"invalid base-13 category total digit: {value!r}")
    return BASE13_DIGITS.index(value)


def encode_totals(totals: Sequence[int]) -> str:
    if len(totals) != 3:
        raise ValueError("totals must contain Current, H1, and H5")
    return "".join(int_to_base13(int(v)) for v in totals)


def decode_totals(text: str) -> tuple[int, int, int]:
    if len(text) != 3:
        raise ValueError("visible totals must have exactly three characters")
    return tuple(base13_to_int(ch) for ch in text)  # type: ignore[return-value]


def encode_fingerprint(patterns: Sequence[Sequence[int | str] | str]) -> str:
    if len(patterns) != 6:
        raise ValueError("category fingerprint requires exactly six subcheck patterns")
    return "".join(encode_pattern(pattern) for pattern in patterns)


def decode_fingerprint(fingerprint: str) -> tuple[str, ...]:
    if len(fingerprint) != 6:
        raise ValueError("category fingerprint must have exactly six glyphs")
    return tuple(decode_glyph(glyph) for glyph in fingerprint)


def totals_from_patterns(
    patterns: Iterable[Sequence[int | str] | str],
) -> tuple[int, int, int]:
    normalized = tuple(_normalize_pattern(pattern) for pattern in patterns)
    if len(normalized) != 6:
        raise ValueError("category totals require exactly six subcheck patterns")

    current = sum(int(pattern[0]) for pattern in normalized)
    h1 = sum(int(pattern[1]) for pattern in normalized)
    h5 = sum(int(pattern[2]) for pattern in normalized)
    return current, h1, h5


def make_category_token(
    category: str, patterns: Sequence[Sequence[int | str] | str]
) -> str:
    cat = category.strip().upper()
    if cat not in CATEGORY_KEYS:
        raise ValueError(f"category must be one of A/B/C/D/E: {category!r}")

    normalized = tuple(_normalize_pattern(pattern) for pattern in patterns)
    totals = totals_from_patterns(normalized)
    return f"{cat}={encode_totals(totals)}:{encode_fingerprint(normalized)}"


def display_category_token(token: str) -> str:
    validation = validate_category_token(token)
    if (
        not validation.valid
        or validation.totals is None
        or validation.fingerprint is None
    ):
        raise ValueError(validation.error or f"invalid category token: {token!r}")
    return f"{encode_totals(validation.totals)}:{validation.fingerprint}"


def validate_category_token(token: str) -> CategoryTokenValidation:
    match = _CATEGORY_TOKEN_RE.fullmatch(str(token))
    if not match:
        return CategoryTokenValidation(
            category=None,
            token=str(token),
            valid=False,
            error="token must match '<category>=<three totals>:<six glyphs>'",
        )

    category, visible_totals_text, fingerprint = match.groups()

    try:
        visible_totals = decode_totals(visible_totals_text)
        patterns = decode_fingerprint(fingerprint)
        decoded_totals = totals_from_patterns(patterns)
    except ValueError as exc:
        return CategoryTokenValidation(
            category=category,
            token=str(token),
            valid=False,
            fingerprint=fingerprint,
            error=str(exc),
        )

    if decoded_totals != visible_totals:
        return CategoryTokenValidation(
            category=category,
            token=str(token),
            valid=False,
            totals=visible_totals,
            decoded_totals=decoded_totals,
            fingerprint=fingerprint,
            patterns=patterns,
            error="visible totals do not match decoded fingerprint totals",
        )

    return CategoryTokenValidation(
        category=category,
        token=str(token),
        valid=True,
        totals=visible_totals,
        decoded_totals=decoded_totals,
        fingerprint=fingerprint,
        patterns=patterns,
    )


def row_checksum(
    *,
    symbol: str,
    asof: str,
    category_tokens: Mapping[str, str] | Sequence[str],
    length: int = 4,
) -> str:
    if length < 2 or length > 8:
        raise ValueError("checksum length must be between 2 and 8 characters")

    symbol_part = symbol.strip().upper()
    asof_part = str(asof).strip()

    if isinstance(category_tokens, Mapping):
        token_part = "|".join(
            f"{cat}={category_tokens[cat]}" for cat in sorted(category_tokens)
        )
    else:
        token_part = "|".join(str(token) for token in category_tokens)

    payload = f"{GLYPH_SPEC_VERSION}|{symbol_part}|{asof_part}|{token_part}"
    crc = zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF
    return f"{crc:08X}"[:length]


def all_glyph_patterns() -> tuple[str, ...]:
    return tuple("".join(parts) for parts in itertools.product("012", repeat=3))
