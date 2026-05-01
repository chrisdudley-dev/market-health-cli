from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from market_health.alert_detectors import AlertCandidate
from market_health.alert_store import apply_migrations, connect


@dataclass(frozen=True)
class AlertHistoryEvent:
    alert_key: str
    severity: str
    ts_utc: str
    alert_type: str = ""


@dataclass(frozen=True)
class AlertCooldownConfig:
    default_cooldown_minutes: int = 60
    critical_cooldown_minutes: int = 15
    system_health_cooldown_minutes: int = 15


@dataclass(frozen=True)
class AlertCooldownDecision:
    candidate: AlertCandidate
    allowed: bool
    reason: str = ""
    matched_event: Optional[AlertHistoryEvent] = None


def _parse_utc(value: str) -> dt.datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _cooldown_minutes(
    candidate: AlertCandidate,
    config: AlertCooldownConfig,
) -> int:
    severity = candidate.severity.lower()
    alert_type = candidate.alert_type.lower()

    if severity in {"critical", "error"}:
        return config.critical_cooldown_minutes
    if alert_type.startswith("system") or alert_type.startswith("health"):
        return config.system_health_cooldown_minutes
    return config.default_cooldown_minutes


def apply_alert_cooldowns(
    *,
    candidates: Iterable[AlertCandidate],
    history: Iterable[AlertHistoryEvent],
    now_utc: str,
    config: AlertCooldownConfig = AlertCooldownConfig(),
) -> Tuple[List[AlertCandidate], List[AlertCooldownDecision]]:
    """Return allowed candidates plus suppression decisions.

    Suppression key is `alert_key`.

    Rules:
    - no same-key history => allow
    - same key but changed severity => allow
    - same key and same severity inside cooldown => suppress
    - critical/system-health candidates can use shorter cooldown windows
    """

    now = _parse_utc(now_utc)
    history_by_key: dict[str, list[AlertHistoryEvent]] = {}
    for event in history:
        history_by_key.setdefault(event.alert_key, []).append(event)

    allowed: List[AlertCandidate] = []
    suppressed: List[AlertCooldownDecision] = []

    for candidate in candidates:
        events = history_by_key.get(candidate.alert_key, [])
        if not events:
            allowed.append(candidate)
            continue

        recent_event = max(events, key=lambda event: _parse_utc(event.ts_utc))

        if recent_event.severity.lower() != candidate.severity.lower():
            allowed.append(candidate)
            continue

        elapsed = now - _parse_utc(recent_event.ts_utc)
        cooldown = dt.timedelta(minutes=_cooldown_minutes(candidate, config))

        if elapsed < cooldown:
            suppressed.append(
                AlertCooldownDecision(
                    candidate=candidate,
                    allowed=False,
                    reason=(
                        "cooldown:"
                        f"{int(elapsed.total_seconds() // 60)}m"
                        f"<{int(cooldown.total_seconds() // 60)}m"
                    ),
                    matched_event=recent_event,
                )
            )
        else:
            allowed.append(candidate)

    return allowed, suppressed


def read_alert_history_from_store(
    *,
    db_path: Path,
    limit: int = 1000,
) -> List[AlertHistoryEvent]:
    """Read prior alert delivery/cooldown state from the M43 alert store."""

    with connect(db_path) as conn:
        apply_migrations(conn)
        rows = conn.execute(
            """
            SELECT alert_key, severity, ts_utc, alert_type
            FROM alerts
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        AlertHistoryEvent(
            alert_key=str(row["alert_key"]),
            severity=str(row["severity"]),
            ts_utc=str(row["ts_utc"]),
            alert_type=str(row["alert_type"] or ""),
        )
        for row in rows
    ]
