from dataclasses import dataclass
from typing import Optional
import os


@dataclass(frozen=True)
class AssetMeta:
    symbol: str
    asset_type: str  # sector | inverse | precious | parking | unsupported
    group: str  # SECTOR | INVERSE | PRECIOUS | PARKING | UNSUPPORTED
    metal_type: Optional[str] = (
        None  # gold | silver | platinum | palladium | basket | None
    )
    is_basket: bool = False


SECTOR_SYMBOLS = [
    "XLC",
    "XLF",
    "XLI",
    "XLB",
    "XLRE",
    "XLU",
    "XLP",
    "XLY",
    "XLK",
    "XLE",
]

INVERSE_SYMBOLS = [
    "TECS",
    "FAZ",
    "ERY",
    "DRV",
    "SIJ",
    "SMN",
    "SDP",
    "SZK",
    "RXD",
    "SCC",
]

PRECIOUS_SYMBOLS = [
    "GLDM",
    "SIVR",
    "PPLT",
    "PALL",
    "GLTR",
]

PRECIOUS_SINGLE_SYMBOLS = [
    "GLDM",
    "SIVR",
    "PPLT",
    "PALL",
]

PARKING_SYMBOLS = [
    "SGOV",
]


def _flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def precious_metals_enabled() -> bool:
    return _flag("MH_ENABLE_PRECIOUS_METALS", "1")


def get_default_scoring_symbols(include_precious: Optional[bool] = None) -> list[str]:
    if include_precious is None:
        include_precious = precious_metals_enabled()

    symbols = list(SECTOR_SYMBOLS)
    if include_precious:
        symbols.extend(PRECIOUS_SYMBOLS)
    return symbols


def classify_asset_symbol(symbol: str) -> AssetMeta:
    sym = symbol.upper().strip()

    if sym in SECTOR_SYMBOLS or (sym.startswith("XL") and len(sym) <= 5):
        return AssetMeta(symbol=sym, asset_type="sector", group="SECTOR")

    if sym in INVERSE_SYMBOLS:
        return AssetMeta(symbol=sym, asset_type="inverse", group="INVERSE")

    if sym == "GLDM":
        return AssetMeta(
            symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="gold"
        )
    if sym == "SIVR":
        return AssetMeta(
            symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="silver"
        )
    if sym == "PPLT":
        return AssetMeta(
            symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="platinum"
        )
    if sym == "PALL":
        return AssetMeta(
            symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="palladium"
        )
    if sym == "GLTR":
        return AssetMeta(
            symbol=sym,
            asset_type="precious",
            group="PRECIOUS",
            metal_type="basket",
            is_basket=True,
        )

    if sym in PARKING_SYMBOLS:
        return AssetMeta(symbol=sym, asset_type="parking", group="PARKING")

    return AssetMeta(symbol=sym, asset_type="unsupported", group="UNSUPPORTED")


def get_asset_meta(symbol: str) -> AssetMeta:
    return classify_asset_symbol(symbol)
