from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Scores:
    symbol: str
    c: Optional[float] = None
    h1: Optional[float] = None
    h5: Optional[float] = None
    blend: Optional[float] = None
    state: str = ""
    price: Optional[float] = None
    stop: Optional[float] = None
    buy: Optional[float] = None
    asof: str = ""
    error: str = ""
    glyph: str = ""


@dataclass(frozen=True)
class Check:
    code: str
    rule: str
    actual: str
    passed: bool


@dataclass(frozen=True)
class Decision:
    symbol: str
    action: str
    reason_codes: tuple[str, ...]
    human_explanation: str
    rescue_active: bool
    rescue_count: int
    can_add: bool
    buy_qualified: bool
    timestamp: str
    checks: tuple[Check, ...]
