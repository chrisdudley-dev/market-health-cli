from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, List, Mapping, Optional

from market_health.alert_detectors import AlertCandidate
from market_health.alert_store import add_system_event, apply_migrations, connect


def _parse_utc(value: str) -> dt.datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _minutes_between(later_utc: str, earlier_utc: str) -> float:
    later = _parse_utc(later_utc)
    earlier = _parse_utc(earlier_utc)
    return (later - earlier).total_seconds() / 60.0


def _system_candidate(
    *,
    key: str,
    severity: str,
    title: str,
    message: str,
    payload: Optional[dict[str, Any]] = None,
) -> AlertCandidate:
    return AlertCandidate(
        alert_key=f"system_health:{key}",
        alert_type=f"system_health_{key}",
        severity=severity,
        title=title,
        message=message,
        payload=payload or {},
    )


def detect_ui_artifact_health(
    *,
    ui_path: Path,
    now_utc: str,
    stale_after_minutes: int = 30,
) -> List[AlertCandidate]:
    """Detect missing, invalid, or stale market-health UI artifacts."""

    if not ui_path.exists():
        return [
            _system_candidate(
                key="ui_artifact_missing",
                severity="critical",
                title="Market-health UI artifact missing",
                message=f"UI artifact is missing: {ui_path}",
                payload={"path": str(ui_path)},
            )
        ]

    try:
        data = json.loads(ui_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            _system_candidate(
                key="ui_artifact_invalid",
                severity="critical",
                title="Market-health UI artifact invalid",
                message=f"UI artifact could not be parsed: {ui_path}",
                payload={"path": str(ui_path), "error": str(exc)},
            )
        ]

    if not isinstance(data, Mapping):
        return [
            _system_candidate(
                key="ui_artifact_invalid",
                severity="critical",
                title="Market-health UI artifact invalid",
                message=f"UI artifact is not a JSON object: {ui_path}",
                payload={"path": str(ui_path)},
            )
        ]

    asof = data.get("asof")
    if not isinstance(asof, str) or not asof.strip():
        return [
            _system_candidate(
                key="ui_artifact_missing_asof",
                severity="warning",
                title="Market-health UI artifact missing asof",
                message=f"UI artifact has no usable asof timestamp: {ui_path}",
                payload={"path": str(ui_path)},
            )
        ]

    try:
        age_minutes = _minutes_between(now_utc, asof)
    except Exception as exc:
        return [
            _system_candidate(
                key="ui_artifact_invalid_asof",
                severity="warning",
                title="Market-health UI artifact has invalid asof",
                message=f"UI artifact asof timestamp is invalid: {asof}",
                payload={"path": str(ui_path), "asof": asof, "error": str(exc)},
            )
        ]

    if age_minutes > stale_after_minutes:
        return [
            _system_candidate(
                key="ui_artifact_stale",
                severity="warning",
                title="Market-health UI artifact is stale",
                message=(
                    f"UI artifact is {age_minutes:.1f} minutes old, exceeding "
                    f"the {stale_after_minutes} minute threshold."
                ),
                payload={
                    "path": str(ui_path),
                    "asof": asof,
                    "age_minutes": age_minutes,
                    "threshold_minutes": stale_after_minutes,
                },
            )
        ]

    return []


def detect_recent_system_failures(
    *,
    db_path: Path,
    now_utc: str,
    lookback_minutes: int = 60,
) -> List[AlertCandidate]:
    """Detect recent stored system-event failures from SQLite."""

    with connect(db_path) as conn:
        apply_migrations(conn)
        rows = conn.execute(
            """
            SELECT event_type, severity, message, ts_utc, payload_json
            FROM system_events
            WHERE LOWER(severity) IN ('warning', 'error', 'critical')
            ORDER BY id DESC
            LIMIT 100
            """
        ).fetchall()

    alerts: List[AlertCandidate] = []
    for row in rows:
        ts_utc = str(row["ts_utc"])
        try:
            age_minutes = _minutes_between(now_utc, ts_utc)
        except Exception:
            continue

        if age_minutes > lookback_minutes:
            continue

        event_type = str(row["event_type"])
        severity = str(row["severity"])
        message = str(row["message"])
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except Exception:
            payload = {}

        alerts.append(
            _system_candidate(
                key=f"recent_{event_type}",
                severity="critical"
                if severity.lower() in {"error", "critical"}
                else "warning",
                title=f"Recent system event: {event_type}",
                message=message,
                payload={
                    "event_type": event_type,
                    "event_severity": severity,
                    "event_ts_utc": ts_utc,
                    "age_minutes": age_minutes,
                    "payload": payload,
                },
            )
        )

    return alerts


def detect_no_recent_successful_run(
    *,
    db_path: Path,
    now_utc: str,
    max_age_minutes: int = 60,
) -> List[AlertCandidate]:
    """Detect whether the alert service has no recent successful run."""

    with connect(db_path) as conn:
        apply_migrations(conn)
        row = conn.execute(
            """
            SELECT finished_at_utc, started_at_utc
            FROM runs
            WHERE status = 'success'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return [
            _system_candidate(
                key="no_successful_run",
                severity="warning",
                title="No successful M43 alert-service run found",
                message="No successful M43 alert-service run is recorded in SQLite.",
                payload={"threshold_minutes": max_age_minutes},
            )
        ]

    ts_utc = str(row["finished_at_utc"] or row["started_at_utc"])
    try:
        age_minutes = _minutes_between(now_utc, ts_utc)
    except Exception as exc:
        return [
            _system_candidate(
                key="invalid_successful_run_timestamp",
                severity="warning",
                title="Latest successful run has invalid timestamp",
                message=f"Latest successful run timestamp is invalid: {ts_utc}",
                payload={"ts_utc": ts_utc, "error": str(exc)},
            )
        ]

    if age_minutes > max_age_minutes:
        return [
            _system_candidate(
                key="no_recent_successful_run",
                severity="warning",
                title="No recent successful M43 alert-service run",
                message=(
                    f"Latest successful run is {age_minutes:.1f} minutes old, "
                    f"exceeding the {max_age_minutes} minute threshold."
                ),
                payload={
                    "latest_success_ts_utc": ts_utc,
                    "age_minutes": age_minutes,
                    "threshold_minutes": max_age_minutes,
                },
            )
        ]

    return []


def collect_system_health_alerts(
    *,
    db_path: Path,
    ui_path: Path,
    now_utc: str,
    artifact_stale_after_minutes: int = 30,
    successful_run_max_age_minutes: int = 60,
    failure_lookback_minutes: int = 60,
) -> List[AlertCandidate]:
    """Collect system-health alert candidates without sending them."""

    alerts: List[AlertCandidate] = []
    alerts.extend(
        detect_ui_artifact_health(
            ui_path=ui_path,
            now_utc=now_utc,
            stale_after_minutes=artifact_stale_after_minutes,
        )
    )
    alerts.extend(
        detect_no_recent_successful_run(
            db_path=db_path,
            now_utc=now_utc,
            max_age_minutes=successful_run_max_age_minutes,
        )
    )
    alerts.extend(
        detect_recent_system_failures(
            db_path=db_path,
            now_utc=now_utc,
            lookback_minutes=failure_lookback_minutes,
        )
    )
    return alerts


def record_system_health_alert(
    *,
    db_path: Path,
    candidate: AlertCandidate,
    run_id: Optional[int] = None,
    ts_utc: Optional[str] = None,
) -> int:
    """Store a system-health candidate as a system_events row."""

    return add_system_event(
        db_path=db_path,
        run_id=run_id,
        ts_utc=ts_utc,
        event_type=candidate.alert_type,
        severity=candidate.severity,
        message=candidate.message,
        payload=candidate.payload,
    )
