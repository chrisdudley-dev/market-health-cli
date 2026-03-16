from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MarketProfile:
    market: str
    region: str
    calendar_id: str
    currency: str
    broad_benchmark: str
    taxonomy: str
    session_model: str
    supports_sector_taxonomy: bool
    supports_inverse_etfs: bool
    supports_crowding_direct: str


@dataclass(frozen=True)
class SymbolMeta:
    symbol: str
    market: str
    region: str
    kind: str
    bucket_id: str
    family_id: str
    benchmark_symbol: str
    calendar_id: str
    currency: str
    taxonomy: str


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_market_profile(path: Path) -> MarketProfile:
    return MarketProfile(**_read_yaml(path))


def load_symbol_catalog(path: Path) -> list[SymbolMeta]:
    data = _read_yaml(path)
    rows = data.get("symbols", [])
    if not isinstance(rows, list):
        raise ValueError("symbols must be a list")
    return [SymbolMeta(**row) for row in rows]


def validate_symbol_against_market(symbol: SymbolMeta, market: MarketProfile) -> None:
    if symbol.market != market.market:
        raise ValueError(f"{symbol.symbol}: market mismatch")
    if symbol.region != market.region:
        raise ValueError(f"{symbol.symbol}: region mismatch")
    if symbol.calendar_id != market.calendar_id:
        raise ValueError(f"{symbol.symbol}: calendar mismatch")
    if symbol.currency != market.currency:
        raise ValueError(f"{symbol.symbol}: currency mismatch")
    if symbol.taxonomy != market.taxonomy:
        raise ValueError(f"{symbol.symbol}: taxonomy mismatch")
