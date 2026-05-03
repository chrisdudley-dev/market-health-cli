from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import requests

from market_health.alert_detectors import AlertCandidate
from market_health.alert_store import add_alert


@dataclass(frozen=True)
class TelegramConfig:
    mode: str = "disabled"
    bot_token: str = ""
    chat_id: str = ""
    api_base: str = "https://api.telegram.org"


@dataclass(frozen=True)
class TelegramDeliveryResult:
    delivery_status: str
    sent: bool
    text: str
    error_text: Optional[str] = None
    delivered_at_utc: Optional[str] = None


Sender = Callable[[str, Mapping[str, str], int], Any]


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_mode(value: str) -> str:
    mode = str(value or "disabled").strip().lower()
    if mode not in {"disabled", "dry-run", "test", "live"}:
        return "disabled"
    return mode


def load_telegram_config(path: Path) -> TelegramConfig:
    """Load Telegram config from a local secrets/config file.

    The file is expected to live outside committed repo paths, for example
    ~/.config/jerboa/telegram.json or a future M43-specific secrets file.
    """

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return TelegramConfig(mode="disabled")
    except Exception:
        return TelegramConfig(mode="disabled")

    if not isinstance(raw, dict):
        return TelegramConfig(mode="disabled")

    return TelegramConfig(
        mode=_clean_mode(str(raw.get("mode", "disabled"))),
        bot_token=str(raw.get("bot_token", "")).strip(),
        chat_id=str(raw.get("chat_id", "")).strip(),
        api_base=str(raw.get("api_base", "https://api.telegram.org")).strip()
        or "https://api.telegram.org",
    )


def _default_sender(url: str, data: Mapping[str, str], timeout: int) -> Any:
    return requests.post(url, data=dict(data), timeout=timeout)


def _fmt_score(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.1f}"
    return "n/a"


def _fmt_threshold(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.1f}"
    return "n/a"


def _score_line(payload: Mapping[str, Any]) -> str:
    return (
        "Scores: "
        f"C={_fmt_score(payload.get('c_score', payload.get('current_score')))} | "
        f"H1={_fmt_score(payload.get('h1_score'))} | "
        f"H5={_fmt_score(payload.get('h5_score'))} | "
        f"blend={_fmt_score(payload.get('blend_score'))}"
    )


def _score_values_line(label: str, values: Mapping[str, Any]) -> str:
    return (
        f"{label}: "
        f"C={_fmt_score(values.get('c_score', values.get('current_score')))} | "
        f"H1={_fmt_score(values.get('h1_score'))} | "
        f"H5={_fmt_score(values.get('h5_score'))} | "
        f"blend={_fmt_score(values.get('blend_score'))}"
    )


def _safe_join(values: Any) -> str:
    if isinstance(values, list):
        return ", ".join(str(v) for v in values if str(v).strip()) or "n/a"
    return str(values) if values is not None else "n/a"


def _format_held_forecast_divergence(candidate: AlertCandidate, *, prefix: str) -> str:
    payload = candidate.payload
    return "\n".join(
        [
            f"{prefix}{candidate.title}",
            f"Severity: {candidate.severity}",
            f"Rule: {payload.get('triggered_rule', 'C>forecast')}",
            _score_line(payload),
            (
                f"Drop: {_fmt_score(payload.get('drop'))} "
                f"points; threshold={_fmt_threshold(payload.get('threshold'))}"
            ),
            f"Reason: {candidate.message}",
        ]
    )


def _format_held_unhealthy_floor(candidate: AlertCandidate, *, prefix: str) -> str:
    payload = candidate.payload
    return "\n".join(
        [
            f"{prefix}{candidate.title}",
            f"Severity: {candidate.severity}",
            "Rule: below healthy floor",
            _score_line(payload),
            f"Healthy floor: {_fmt_threshold(payload.get('healthy_floor'))}",
            f"Breached: {_safe_join(payload.get('breached_fields'))}",
            f"Reason: {candidate.message}",
        ]
    )


def _format_held_band_state_degraded(candidate: AlertCandidate, *, prefix: str) -> str:
    payload = candidate.payload
    previous_values = payload.get("previous_values")
    current_values = payload.get("current_values")
    previous_values = previous_values if isinstance(previous_values, Mapping) else {}
    current_values = current_values if isinstance(current_values, Mapping) else {}

    return "\n".join(
        [
            f"{prefix}{candidate.title}",
            f"Severity: {candidate.severity}",
            "Rule: held state/score degradation",
            (
                f"State: {payload.get('previous_state', 'n/a')} -> "
                f"{payload.get('current_state', 'n/a')}"
            ),
            _score_values_line("Previous", previous_values),
            _score_values_line("Current", current_values),
            f"Degraded fields: {_safe_join(payload.get('degraded_fields'))}",
            f"Reason: {payload.get('reason') or candidate.message}",
        ]
    )


def _format_held_significant_score_drop(
    candidate: AlertCandidate, *, prefix: str
) -> str:
    payload = candidate.payload
    previous_values = payload.get("previous_values")
    current_values = payload.get("current_values")
    previous_values = previous_values if isinstance(previous_values, Mapping) else {}
    current_values = current_values if isinstance(current_values, Mapping) else {}
    drops = payload.get("drops")
    drops = drops if isinstance(drops, Mapping) else {}
    affected = payload.get("affected_fields")

    drop_text = ", ".join(
        f"{field} -{_fmt_score(drops.get(field))}"
        for field in affected
        if isinstance(affected, list)
    )

    return "\n".join(
        [
            f"{prefix}{candidate.title}",
            f"Severity: {candidate.severity}",
            "Rule: significant score drop",
            _score_values_line("Previous", previous_values),
            _score_values_line("Current", current_values),
            f"Drops: {drop_text or 'n/a'}",
            f"Threshold: {_fmt_threshold(payload.get('threshold'))}",
            f"Affected: {_safe_join(affected)}",
        ]
    )


def format_alert_message(
    candidate: AlertCandidate,
    *,
    test_prefix: bool = False,
) -> str:
    prefix = "TEST: " if test_prefix else ""

    if candidate.alert_type == "held_forecast_divergence":
        return _format_held_forecast_divergence(candidate, prefix=prefix)

    if candidate.alert_type == "held_unhealthy_floor":
        return _format_held_unhealthy_floor(candidate, prefix=prefix)

    if candidate.alert_type == "held_band_state_degraded":
        return _format_held_band_state_degraded(candidate, prefix=prefix)

    if candidate.alert_type == "held_significant_score_drop":
        return _format_held_significant_score_drop(candidate, prefix=prefix)

    parts = [
        f"{prefix}{candidate.title}",
        candidate.message,
    ]
    if candidate.symbol:
        parts.append(f"Symbol: {candidate.symbol}")
    parts.append(f"Severity: {candidate.severity}")
    parts.append(f"Type: {candidate.alert_type}")
    return "\n".join(part for part in parts if part)


def send_alert_candidate(
    candidate: AlertCandidate,
    *,
    config: TelegramConfig,
    sender: Sender = _default_sender,
    timeout: int = 10,
    now_utc: Optional[str] = None,
) -> TelegramDeliveryResult:
    mode = _clean_mode(config.mode)
    text = format_alert_message(candidate, test_prefix=(mode == "test"))

    if mode == "disabled":
        return TelegramDeliveryResult(
            delivery_status="disabled",
            sent=False,
            text=text,
        )

    if mode == "dry-run":
        return TelegramDeliveryResult(
            delivery_status="dry-run",
            sent=False,
            text=text,
        )

    if not config.bot_token or not config.chat_id:
        return TelegramDeliveryResult(
            delivery_status="error",
            sent=False,
            text=text,
            error_text="missing telegram bot_token or chat_id",
        )

    url = f"{config.api_base.rstrip('/')}/bot{config.bot_token}/sendMessage"
    try:
        response = sender(
            url,
            {"chat_id": config.chat_id, "text": text},
            timeout,
        )
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
    except Exception as exc:
        return TelegramDeliveryResult(
            delivery_status="error",
            sent=False,
            text=text,
            error_text=str(exc),
        )

    return TelegramDeliveryResult(
        delivery_status="sent",
        sent=True,
        text=text,
        delivered_at_utc=now_utc or _utc_now_iso(),
    )


def send_and_record_alert_candidate(
    *,
    db_path: Path,
    run_id: int,
    candidate: AlertCandidate,
    config: TelegramConfig,
    sender: Sender = _default_sender,
    timeout: int = 10,
    ts_utc: Optional[str] = None,
) -> TelegramDeliveryResult:
    result = send_alert_candidate(
        candidate,
        config=config,
        sender=sender,
        timeout=timeout,
        now_utc=ts_utc,
    )

    add_alert(
        db_path=db_path,
        run_id=run_id,
        alert_key=candidate.alert_key,
        alert_type=candidate.alert_type,
        severity=candidate.severity,
        symbol=candidate.symbol,
        title=candidate.title,
        message=candidate.message,
        payload={
            **candidate.payload,
            "telegram_text": result.text,
        },
        ts_utc=ts_utc,
        delivery_status=result.delivery_status,
        delivered_at_utc=result.delivered_at_utc,
        error_text=result.error_text,
    )
    return result
