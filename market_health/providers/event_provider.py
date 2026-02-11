from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/jerboa/event_provider.json")


@dataclass(frozen=True)
class EventPoint:
    ts: str
    symbol: str
    type: str
    headline: str
    impact: float
    confidence: float
    extra: Dict[str, Any]


@dataclass(frozen=True)
class EventBundle:
    schema: str
    status: str                 # "ok" | "no_provider" | "error"
    generated_at: str
    source: Dict[str, Any]
    points: List[EventPoint]
    errors: List[str]


class EventProvider:
    def get_events(self, symbols: List[str]) -> EventBundle:
        raise NotImplementedError


class NullEventProvider(EventProvider):
    def get_events(self, symbols: List[str]) -> EventBundle:
        return EventBundle(
            schema="events.v1",
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


class StubEventProvider(EventProvider):
    """
    Offline-only provider reading docs/examples/events_stub.sample.json shape.
    """

    def __init__(self, stub_path: str):
        self.stub_path = os.path.expanduser(stub_path)

    def get_events(self, symbols: List[str]) -> EventBundle:
        errors: List[str] = []
        try:
            doc = _read_json(self.stub_path)
        except FileNotFoundError:
            return EventBundle(
                schema="events.v1",
                status="error",
                generated_at="",
                source={"type": "stub", "path": self.stub_path},
                points=[],
                errors=[f"file not found: {self.stub_path}"],
            )
        except Exception as e:
            return EventBundle(
                schema="events.v1",
                status="error",
                generated_at="",
                source={"type": "stub", "path": self.stub_path},
                points=[],
                errors=[f"failed to read stub: {e}"],
            )

        generated_at = str(doc.get("generated_at", ""))
        source = doc.get("source") if isinstance(doc.get("source"), dict) else {"type": "stub"}
        if str(doc.get("schema", "")) != "events.stub.v1":
            errors.append('schema must be "events.stub.v1" for stub input')

        evs = doc.get("events")
        if not isinstance(evs, list):
            return EventBundle(
                schema="events.v1",
                status="error",
                generated_at=generated_at,
                source=source,
                points=[],
                errors=errors + ["events must be an array"],
            )

        want = set([s.strip() for s in symbols if s.strip()])
        points: List[EventPoint] = []
        for i, e in enumerate(evs):
            if not isinstance(e, dict):
                errors.append(f"events[{i}] must be an object")
                continue
            sym = str(e.get("symbol", "")).strip()
            if want and sym not in want:
                continue

            ts = str(e.get("ts", "")).strip()
            typ = str(e.get("type", "")).strip()
            headline = str(e.get("headline", "")).strip()
            if not ts or not sym or not typ or not headline:
                errors.append(f"events[{i}] missing required fields (ts/symbol/type/headline)")
                continue

            points.append(
                EventPoint(
                    ts=ts,
                    symbol=sym,
                    type=typ,
                    headline=headline,
                    impact=_as_float(e.get("impact", 0.0)),
                    confidence=_as_float(e.get("confidence", 0.0)),
                    extra={k: v for k, v in e.items() if k not in ("ts", "symbol", "type", "headline", "impact", "confidence")},
                )
            )

        status = "ok" if points and not errors else ("ok" if points else ("error" if errors else "ok"))
        return EventBundle(
            schema="events.v1",
            status=status if status != "error" else "error",
            generated_at=generated_at,
            source=source,
            points=points,
            errors=errors,
        )


def load_event_provider(config_path: str = DEFAULT_CONFIG_PATH) -> EventProvider:
    """
    config example (~/.config/jerboa/event_provider.json):
      { "provider": "stub", "stub_path": "docs/examples/events_stub.sample.json" }
    """
    p = os.path.expanduser(config_path)
    if not os.path.exists(p):
        return NullEventProvider()
    try:
        d = _read_json(p)
    except Exception:
        return NullEventProvider()

    provider = str(d.get("provider", "")).strip().lower()
    if provider == "stub":
        stub_path = str(d.get("stub_path", "")).strip()
        if not stub_path:
            return NullEventProvider()
        return StubEventProvider(stub_path)
    return NullEventProvider()
