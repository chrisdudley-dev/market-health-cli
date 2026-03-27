from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
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
    tradable_live: bool = True
    listing_country: str = ""
    primary_exchange: str = ""
    execution_class: str = ""
    broker_profile: str = "us_retail_supported"


@dataclass(frozen=True)
class TaxonomyBridgeEntry:
    bucket_id: str
    family_id: str
    representative_symbol: str


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_market_profile(path: Path) -> MarketProfile:
    return MarketProfile(**_read_yaml(path))


def load_symbol_catalog(path: Path) -> list[SymbolMeta]:
    data = _read_yaml(path)
    rows = data.get("symbols", [])
    if not isinstance(rows, list):
        raise ValueError("symbols must be a list")
    return [SymbolMeta(**row) for row in rows]


def load_taxonomy_bridge(path: Path) -> dict[str, TaxonomyBridgeEntry]:
    data = _read_yaml(path)
    bridge = data.get("bridge", {})
    if not isinstance(bridge, dict):
        raise ValueError("bridge must be a mapping")

    out: dict[str, TaxonomyBridgeEntry] = {}
    for bucket_id, row in bridge.items():
        if not isinstance(bucket_id, str) or not bucket_id.strip():
            raise ValueError("bridge keys must be non-empty strings")
        if not isinstance(row, dict):
            raise ValueError(f"{bucket_id}: bridge entry must be a mapping")
        out[bucket_id] = TaxonomyBridgeEntry(
            bucket_id=bucket_id,
            family_id=str(row["family_id"]),
            representative_symbol=str(row["representative_symbol"]),
        )
    return out


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


def validate_symbol_against_bridge(
    symbol: SymbolMeta,
    bridge: dict[str, TaxonomyBridgeEntry],
) -> None:
    entry = bridge.get(symbol.bucket_id)
    if entry is None:
        raise ValueError(f"{symbol.symbol}: bucket_id missing from taxonomy bridge")
    if symbol.family_id != entry.family_id:
        raise ValueError(
            f"{symbol.symbol}: family_id mismatch for bucket {symbol.bucket_id}"
        )


@lru_cache(maxsize=1)
def get_symbol_catalog() -> list[SymbolMeta]:
    return load_symbol_catalog(
        _repo_root() / "config" / "symbols" / "global_markets.yaml"
    )


@lru_cache(maxsize=None)
def load_market_profile_for_market(market: str) -> MarketProfile:
    return load_market_profile(
        _repo_root() / "config" / "markets" / f"{market.lower()}.yaml"
    )


@lru_cache(maxsize=None)
def get_taxonomy_bridge_for_market(market: str) -> dict[str, TaxonomyBridgeEntry]:
    return load_taxonomy_bridge(
        _repo_root() / "config" / "taxonomy" / f"{market.lower()}_topix17_bridge.yaml"
    )


def get_symbol_meta(symbol: str) -> SymbolMeta | None:
    symbol_u = symbol.strip().upper()
    for meta in get_symbol_catalog():
        if meta.symbol.upper() == symbol_u:
            return meta
    return None


def get_market_profile_for_symbol(symbol: str) -> MarketProfile | None:
    meta = get_symbol_meta(symbol)
    if meta is None:
        return None
    return load_market_profile_for_market(meta.market)


def get_taxonomy_bridge_entry_for_symbol(symbol: str) -> TaxonomyBridgeEntry | None:
    meta = get_symbol_meta(symbol)
    if meta is None:
        return None
    bridge = get_taxonomy_bridge_for_market(meta.market)
    return bridge.get(meta.bucket_id)


def get_live_symbol_catalog() -> list[SymbolMeta]:
    return [m for m in get_symbol_catalog() if bool(getattr(m, "tradable_live", True))]


def is_symbol_live_tradable(symbol: str) -> bool:
    meta = get_symbol_meta(symbol)
    if meta is None:
        return True
    return bool(getattr(meta, "tradable_live", True))
