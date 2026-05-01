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


def format_alert_message(
    candidate: AlertCandidate,
    *,
    test_prefix: bool = False,
) -> str:
    prefix = "TEST: " if test_prefix else ""
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
