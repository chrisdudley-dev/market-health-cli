from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class AssetMeta:
    symbol: str
    asset_type: str   # sector | inverse | precious | parking
    group: str        # SECTOR | INVERSE | PRECIOUS | PARKING
    metal_type: Optional[str] = None  # gold | silver | platinum | palladium | basket | None
    is_basket: bool = False


SECTOR_SYMBOLS = [
    "XLC", "XLF", "XLI", "XLB", "XLRE", "XLU", "XLP", "XLY", "XLK", "XLE",
]

INVERSE_SYMBOLS = [
    "TECS", "FAZ", "ERY", "DRV", "SIJ", "SMN", "SDP", "SZK", "RXD", "SCC",
]

PRECIOUS_SYMBOLS = [
    "GLDM", "SIVR", "PPLT", "PALL", "GLTR",
]

PARKING_SYMBOLS = [
    "SGOV",
]


def get_asset_meta(symbol: str) -> AssetMeta:
    sym = symbol.upper().strip()

    if sym in SECTOR_SYMBOLS:
        return AssetMeta(symbol=sym, asset_type="sector", group="SECTOR")

    if sym in INVERSE_SYMBOLS:
        return AssetMeta(symbol=sym, asset_type="inverse", group="INVERSE")

    if sym == "GLDM":
        return AssetMeta(symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="gold")
    if sym == "SIVR":
        return AssetMeta(symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="silver")
    if sym == "PPLT":
        return AssetMeta(symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="platinum")
    if sym == "PALL":
        return AssetMeta(symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="palladium")
    if sym == "GLTR":
        return AssetMeta(symbol=sym, asset_type="precious", group="PRECIOUS", metal_type="basket", is_basket=True)

    if sym in PARKING_SYMBOLS:
        return AssetMeta(symbol=sym, asset_type="parking", group="PARKING")

    return AssetMeta(symbol=sym, asset_type="sector", group="SECTOR")
