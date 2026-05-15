from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from market_health.glyph_spec import (
    CATEGORY_KEYS,
    GLYPH_SPEC_VERSION,
    display_category_token,
    make_category_token,
    row_checksum,
    validate_category_token,
)


@dataclass(frozen=True)
class CategoryAuditCell:
    category: str
    token: str | None
    display_token: str
    valid: bool
    totals: tuple[int, int, int] | None = None
    fingerprint: str | None = None
    patterns: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class SymbolAuditRow:
    symbol: str
    asof: str
    cells: dict[str, CategoryAuditCell]
    checksum: str
    is_held: bool = False
    glyph_spec_version: str = GLYPH_SPEC_VERSION

    @property
    def all_valid(self) -> bool:
        return all(cell.valid for cell in self.cells.values())

    @property
    def display_cells(self) -> dict[str, str]:
        return {category: cell.display_token for category, cell in self.cells.items()}

    @property
    def canonical_tokens(self) -> dict[str, str]:
        return {
            category: cell.token
            for category, cell in self.cells.items()
            if cell.token is not None
        }


def _error_cell(category: str, error: str) -> CategoryAuditCell:
    return CategoryAuditCell(
        category=category,
        token=None,
        display_token="BAD",
        valid=False,
        error=error,
    )


def _cat_node(payload: Mapping[str, Any], category: str) -> Any:
    categories = payload.get("categories")
    if isinstance(categories, Mapping):
        return categories.get(category)
    return payload.get(category)


def _checks_for_category(
    payload: Mapping[str, Any], category: str
) -> list[Mapping[str, Any]]:
    node = _cat_node(payload, category)
    if isinstance(node, Mapping) and isinstance(node.get("checks"), list):
        checks = [check for check in node["checks"] if isinstance(check, Mapping)]
    elif isinstance(node, list):
        checks = [check for check in node if isinstance(check, Mapping)]
    else:
        raise ValueError(f"missing category payload for {category}")

    if len(checks) != 6:
        raise ValueError(f"category {category} must contain exactly six checks")

    return checks


def _score_digit(check: Mapping[str, Any], *, category: str, index: int) -> str:
    value = check.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"category {category} check {index + 1} has no numeric score")

    if int(value) != value:
        raise ValueError(
            f"category {category} check {index + 1} score must be 0, 1, or 2"
        )

    score = int(value)
    if score < 0 or score > 2:
        raise ValueError(
            f"category {category} check {index + 1} score must be 0, 1, or 2"
        )

    return str(score)


def category_patterns_from_payloads(
    *,
    category: str,
    current_payload: Mapping[str, Any],
    h1_payload: Mapping[str, Any],
    h5_payload: Mapping[str, Any],
) -> tuple[str, ...]:
    cat = category.strip().upper()
    if cat not in CATEGORY_KEYS:
        raise ValueError(f"category must be one of A/B/C/D/E: {category!r}")

    current_checks = _checks_for_category(current_payload, cat)
    h1_checks = _checks_for_category(h1_payload, cat)
    h5_checks = _checks_for_category(h5_payload, cat)

    patterns: list[str] = []
    for index in range(6):
        patterns.append(
            _score_digit(current_checks[index], category=cat, index=index)
            + _score_digit(h1_checks[index], category=cat, index=index)
            + _score_digit(h5_checks[index], category=cat, index=index)
        )

    return tuple(patterns)


def build_category_audit_cell(
    *,
    category: str,
    current_payload: Mapping[str, Any],
    h1_payload: Mapping[str, Any],
    h5_payload: Mapping[str, Any],
) -> CategoryAuditCell:
    cat = category.strip().upper()

    try:
        patterns = category_patterns_from_payloads(
            category=cat,
            current_payload=current_payload,
            h1_payload=h1_payload,
            h5_payload=h5_payload,
        )
        token = make_category_token(cat, patterns)
        validation = validate_category_token(token)
        if not validation.valid:
            return _error_cell(cat, validation.error or "invalid category token")

        return CategoryAuditCell(
            category=cat,
            token=token,
            display_token=display_category_token(token),
            valid=True,
            totals=validation.totals,
            fingerprint=validation.fingerprint,
            patterns=validation.patterns,
        )
    except ValueError as exc:
        return _error_cell(cat, str(exc))


def build_symbol_audit_row(
    *,
    symbol: str,
    asof: str,
    current_payload: Mapping[str, Any],
    h1_payload: Mapping[str, Any],
    h5_payload: Mapping[str, Any],
    is_held: bool = False,
) -> SymbolAuditRow:
    symbol_u = symbol.strip().upper()
    cells = {
        category: build_category_audit_cell(
            category=category,
            current_payload=current_payload,
            h1_payload=h1_payload,
            h5_payload=h5_payload,
        )
        for category in CATEGORY_KEYS
    }

    checksum_inputs = [
        cell.token
        if cell.token is not None
        else f"{cell.category}=INVALID:{cell.error or ''}"
        for cell in cells.values()
    ]

    checksum = row_checksum(
        symbol=symbol_u,
        asof=str(asof),
        category_tokens=checksum_inputs,
    )

    return SymbolAuditRow(
        symbol=symbol_u,
        asof=str(asof),
        cells=cells,
        checksum=checksum,
        is_held=is_held,
    )
