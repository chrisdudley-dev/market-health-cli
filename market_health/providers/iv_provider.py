from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/jerboa/iv_provider.json")

@dataclass(frozen=True)
class IVPoint:
    symbol: str
    iv: float
    iv_rank_1y: float
    iv_percentile_1y: float
    extra: Dict[str, Any]

@dataclass(frozen=True)
class IVBundle:
    schema: str                 # "iv.v1"
    status: str                 # "ok" | "no_provider" | "error"
    generated_at: str
    source: Dict[str, Any]
    points: List[IVPoint]
    errors: List[str]

class IVProvider:
    def get_iv(self, symbols: List[str]) -> IVBundle:
        raise NotImplementedError

class NullIVProvider(IVProvider):
    def get_iv(self, symbols: List[str]) -> IVBundle:
        return IVBundle(
            schema="iv.v1",
            status="no_provider",
            generated_at="",
            source={"type": "null"},
            points=[],
            errors=[],
        )

def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default

class StubIVProvider(IVProvider):
    """
    Offline-only provider reading docs/examples/iv_stub.sample.json shape.
    """
    def __init__(self, stub_path: str):
        self.stub_path = os.path.expanduser(stub_path)

    def get_iv(self, symbols: List[str]) -> IVBundle:
        try:
            doc = _read_json(self.stub_path)
        except FileNotFoundError:
            return IVBundle(
                schema="iv.v1",
                status="error",
                generated_at="",
                source={"type": "stub", "path": self.stub_path},
                points=[],
                errors=[f"file not found: {self.stub_path}"],
            )
        except Exception as e:
            return IVBundle(
                schema="iv.v1",
                status="error",
                generated_at="",
                source={"type": "stub", "path": self.stub_path},
                points=[],
                errors=[f"read error: {e}"],
            )

        sym_map = doc.get("symbols") if isinstance(doc, dict) else None
        if not isinstance(sym_map, dict):
            return IVBundle(
                schema="iv.v1",
                status="error",
                generated_at=str(doc.get("generated_at", "")) if isinstance(doc, dict) else "",
                source=doc.get("source", {"type": "stub"}) if isinstance(doc, dict) else {"type": "stub"},
                points=[],
                errors=["invalid stub: missing object at key 'symbols'"],
            )

        pts: List[IVPoint] = []
        wanted = [str(x).strip().upper() for x in (symbols or []) if str(x).strip()]
        for sym in wanted:
            row = sym_map.get(sym)
            if not isinstance(row, dict):
                continue
            pts.append(
                IVPoint(
                    symbol=sym,
                    iv=_as_float(row.get("iv", 0.0)),
                    iv_rank_1y=_as_float(row.get("iv_rank_1y", 0.0)),
                    iv_percentile_1y=_as_float(row.get("iv_percentile_1y", 0.0)),
                    extra={k: v for k, v in row.items() if k not in ("iv", "iv_rank_1y", "iv_percentile_1y")},
                )
            )

        return IVBundle(
            schema="iv.v1",
            status="ok",
            generated_at=str(doc.get("generated_at", "")),
            source=doc.get("source", {"type": "stub"}) if isinstance(doc, dict) else {"type": "stub"},
            points=pts,
            errors=[],
        )

def load_iv_provider(config_path: str = DEFAULT_CONFIG_PATH) -> IVProvider:
    p = os.path.expanduser(config_path)
    if not os.path.exists(p):
        return NullIVProvider()
    try:
        cfg = _read_json(p)
    except Exception:
        return NullIVProvider()
    provider = str(cfg.get("provider", "null")).strip().lower()
    if provider == "stub":
        stub_path = str(cfg.get("stub_path", "docs/examples/iv_stub.sample.json"))
        return StubIVProvider(stub_path)
    return NullIVProvider()
