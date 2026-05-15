from __future__ import annotations

import re
from typing import Iterable

from market_health.forecast_audit import SymbolAuditRow
from market_health.glyph_spec import GLYPH_SPEC_VERSION, base13_to_int, decode_glyph

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN = "\033[36m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(value: str) -> int:
    return len(ANSI_RE.sub("", value))


def _pad(value: str, width: int) -> str:
    return value + (" " * max(0, width - _visible_len(value)))


def _ansi(value: str, enabled: bool) -> str:
    return value if enabled else ""


def _total_color(value: int) -> str:
    if value <= 3:
        return RED
    if value <= 7:
        return YELLOW
    return GREEN


def _glyph_color(glyph: str) -> str:
    pattern = decode_glyph(glyph)
    score = sum(int(ch) for ch in pattern)
    if score <= 2:
        return RED
    if score <= 3:
        return YELLOW
    return GREEN


def color_display_token(display_token: str, *, color: bool = True) -> str:
    if display_token == "BAD":
        return f"{_ansi(RED, color)}BAD{_ansi(RESET, color)}"

    if ":" not in display_token:
        return display_token

    totals, fingerprint = display_token.split(":", 1)
    if len(totals) != 3 or len(fingerprint) != 6:
        return f"{_ansi(RED, color)}BAD{_ansi(RESET, color)}"

    parts: list[str] = []

    for digit in totals:
        try:
            value = base13_to_int(digit)
        except ValueError:
            return f"{_ansi(RED, color)}BAD{_ansi(RESET, color)}"
        parts.append(f"{_ansi(_total_color(value), color)}{digit}{_ansi(RESET, color)}")

    parts.append(":")

    for glyph in fingerprint:
        try:
            color_code = _glyph_color(glyph)
        except ValueError:
            return f"{_ansi(RED, color)}BAD{_ansi(RESET, color)}"
        parts.append(f"{_ansi(color_code, color)}{glyph}{_ansi(RESET, color)}")

    return "".join(parts)


def render_glyph_audit_overview(
    rows: Iterable[SymbolAuditRow],
    *,
    color: bool = True,
) -> str:
    rows = list(rows)

    widths = {
        "Sym": 7,
        "A": 14,
        "B": 14,
        "C": 14,
        "D": 14,
        "E": 14,
        "ck": 6,
    }
    headers = ["Sym", "A", "B", "C", "D", "E", "ck"]

    out: list[str] = []
    out.append(
        f"{_ansi(BOLD, color)}Market Health — Glyph Audit Overview • {GLYPH_SPEC_VERSION}{_ansi(RESET, color)}"
    )
    out.append(
        f"{_ansi(DIM, color)}cell=totals:fingerprint   totals=C/H1/H5   •=held{_ansi(RESET, color)}"
    )
    out.append("")
    out.append(
        " ".join(
            _pad(f"{_ansi(BOLD, color)}{header}{_ansi(RESET, color)}", widths[header])
            for header in headers
        )
    )
    out.append(" ".join("─" * widths[header] for header in headers))

    for row in rows:
        symbol = row.symbol + ("•" if row.is_held else "")
        checksum = row.checksum if row.all_valid else "FAIL"
        checksum_color = DIM if row.all_valid else RED

        cells = [
            f"{_ansi(CYAN, color)}{symbol}{_ansi(RESET, color)}",
            color_display_token(row.display_cells.get("A", "BAD"), color=color),
            color_display_token(row.display_cells.get("B", "BAD"), color=color),
            color_display_token(row.display_cells.get("C", "BAD"), color=color),
            color_display_token(row.display_cells.get("D", "BAD"), color=color),
            color_display_token(row.display_cells.get("E", "BAD"), color=color),
            f"{_ansi(checksum_color, color)}{checksum}{_ansi(RESET, color)}",
        ]

        out.append(
            " ".join(
                _pad(cells[index], widths[headers[index]])
                for index in range(len(headers))
            )
        )

    return "\n".join(out)
