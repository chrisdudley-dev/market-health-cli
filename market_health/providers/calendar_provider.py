from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/jerboa/calendar_provider.json")

@dataclass(frozen=True)
class CalendarEvent:
    ts: str
    symbol: str
    kind: str                 # earnings | ex_dividend | split | macro | ...
    label: str
    extra: Dict[str, Any]

@dataclass(frozen=True)
class CalendarBundle:
    schema: str               # "calendar.v1"
    status: str               # "ok" | "no_provider" | "error"
    generated_at: str
    source: Dict[str, Any]
    events: List[CalendarEvent]
    errors: List[str]

class CalendarProvider:
    def get_calendar(self, symbols: List[str]) -> CalendarBundle:
        raise NotImplementedError

class NullCalendarProvider(CalendarProvider):
    def get_calendar(self, symbols: List[str]) -> CalendarBundle:
        return CalendarBundle(
            schema="calendar.v1",
            status="no_provider",
            generated_at="",
            source={"type": "null"},
            events=[],
            errors=[],
        )

def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

class StubCalendarProvider(CalendarProvider):
    """
    Offline-only provider reading docs/examples/calendar_stub.sample.json shape.
    """
    def __init__(self, stub_path: str):
        self.stub_path = os.path.expanduser(stub_path)

    def get_calendar(self, symbols: List[str]) -> CalendarBundle:
        try:
            doc = _read_json(self.stub_path)
        except FileNotFoundError:
            return CalendarBundle(
                schema="calendar.v1",
                status="error",
                generated_at="",
                source={"type": "stub", "path": self.stub_path},
                events=[],
                errors=[f"file not found: {self.stub_path}"],
            )
        except Exception as e:
            return CalendarBundle(
                schema="calendar.v1",
                status="error",
                generated_at="",
                source={"type": "stub", "path": self.stub_path},
                events=[],
                errors=[f"read error: {e}"],
            )

        evs = doc.get("events") if isinstance(doc, dict) else None
        if not isinstance(evs, list):
            return CalendarBundle(
                schema="calendar.v1",
                status="error",
                generated_at=str(doc.get("generated_at", "")) if isinstance(doc, dict) else "",
                source=doc.get("source", {"type": "stub"}) if isinstance(doc, dict) else {"type": "stub"},
                events=[],
                errors=["invalid stub: missing list at key 'events'"],
            )

        wanted = {str(x).strip().upper() for x in (symbols or []) if str(x).strip()}
        out: List[CalendarEvent] = []
        for item in evs:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol", "")).strip().upper()
            if wanted and sym not in wanted:
                continue
            out.append(
                CalendarEvent(
                    ts=str(item.get("ts", "")).strip(),
                    symbol=sym,
                    kind=str(item.get("kind", "")).strip(),
                    label=str(item.get("label", "")).strip(),
                    extra=item.get("extra", {}) if isinstance(item.get("extra", {}), dict) else {},
                )
            )

        return CalendarBundle(
            schema="calendar.v1",
            status="ok",
            generated_at=str(doc.get("generated_at", "")),
            source=doc.get("source", {"type": "stub"}) if isinstance(doc, dict) else {"type": "stub"},
            events=out,
            errors=[],
        )

def load_calendar_provider(config_path: str = DEFAULT_CONFIG_PATH) -> CalendarProvider:
    p = os.path.expanduser(config_path)
    if not os.path.exists(p):
        return NullCalendarProvider()
    try:
        cfg = _read_json(p)
    except Exception:
        return NullCalendarProvider()
    provider = str(cfg.get("provider", "null")).strip().lower()
    if provider == "stub":
        stub_path = str(cfg.get("stub_path", "docs/examples/calendar_stub.sample.json"))
        return StubCalendarProvider(stub_path)
    return NullCalendarProvider()
