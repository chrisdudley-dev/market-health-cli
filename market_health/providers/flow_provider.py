from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

DEFAULT_FLOW_CONFIG = os.path.expanduser("~/.config/jerboa/flow_provider.json")

# -------------------------
# Internal normalized model
# -------------------------

@dataclass(frozen=True)
class FlowPoint:
    symbol: str
    metrics: Dict[str, float]

@dataclass(frozen=True)
class FlowBatch:
    schema: str
    generated_at: str
    source: Dict[str, Any]
    points: List[FlowPoint]
    status: str  # "ok" | "no_provider" | "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "source": self.source,
            "status": self.status,
            "points": [{"symbol": p.symbol, "metrics": p.metrics} for p in self.points],
        }

# -------------------------
# Provider interface
# -------------------------

class FlowProvider(Protocol):
    def describe(self) -> str: ...
    def get_flow(self, symbols: List[str]) -> FlowBatch: ...

# -------------------------
# Null provider (graceful)
# -------------------------

class NullFlowProvider:
    def describe(self) -> str:
        return "null (no provider configured)"

    def get_flow(self, symbols: List[str]) -> FlowBatch:
        # Always safe: empty batch, no exceptions.
        return FlowBatch(
            schema="flow.v1",
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            source={"type": "none"},
            points=[],
            status="no_provider",
        )

# -------------------------
# Stub provider (fixture)
# -------------------------

class StubFlowProvider:
    """
    Reads a local JSON fixture and normalizes it to FlowBatch.

    Expected stub shape:
    {
      "schema": "flow.stub.v1",
      "generated_at": "...",
      "source": {...},
      "symbols": { "SPY": { "call_put_ratio": 1.2, ... }, ... }
    }
    """
    def __init__(self, path: str) -> None:
        self.path = os.path.expanduser(path)

    def describe(self) -> str:
        return f"stub (path={self.path})"

    def _load(self) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_flow(self, symbols: List[str]) -> FlowBatch:
        try:
            raw = self._load()
        except FileNotFoundError:
            return FlowBatch(
                schema="flow.v1",
                generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                source={"type": "stub", "path": self.path},
                points=[],
                status="error",
            )
        sym_map = raw.get("symbols") or {}
        points: List[FlowPoint] = []

        # If caller provides symbols, filter; else include all from fixture.
        want = set(s.upper() for s in symbols) if symbols else None

        for sym, metrics in sym_map.items():
            sym_u = str(sym).upper()
            if want is not None and sym_u not in want:
                continue
            if not isinstance(metrics, dict):
                continue
            norm: Dict[str, float] = {}
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    norm[str(k)] = float(v)
                else:
                    # ignore non-numeric (provider-specific noise)
                    continue
            points.append(FlowPoint(symbol=sym_u, metrics=norm))

        return FlowBatch(
            schema="flow.v1",
            generated_at=str(raw.get("generated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            source=dict(raw.get("source") or {"type": "stub", "path": self.path}),
            points=points,
            status="ok",
        )

# -------------------------
# Loader
# -------------------------

def load_flow_provider(config_path: str = DEFAULT_FLOW_CONFIG) -> FlowProvider:
    p = os.path.expanduser(config_path)
    if not os.path.exists(p):
        return NullFlowProvider()
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return NullFlowProvider()

    typ = str(cfg.get("type") or "").lower().strip()
    if typ == "stub":
        path = str(cfg.get("path") or "").strip()
        if not path:
            return NullFlowProvider()
        return StubFlowProvider(path)
    # Unknown provider type -> safe fallback
    return NullFlowProvider()
