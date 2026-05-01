import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

from market_health.alert_detectors import AlertCandidate
from market_health.alert_store import start_run
from market_health.telegram_notifier import (
    TelegramConfig,
    format_alert_message,
    load_telegram_config,
    send_alert_candidate,
    send_and_record_alert_candidate,
)


def _candidate() -> AlertCandidate:
    return AlertCandidate(
        alert_key="position_state:SPY:clean->DMG",
        alert_type="position_state_changed",
        severity="warning",
        symbol="SPY",
        title="SPY state changed",
        message="SPY changed from clean to DMG.",
        payload={"from": "clean", "to": "DMG"},
    )


def test_load_telegram_config_from_local_json(tmp_path: Path) -> None:
    cfg_path = tmp_path / "telegram.json"
    cfg_path.write_text(
        json.dumps(
            {
                "mode": "test",
                "bot_token": "token",
                "chat_id": "chat",
                "api_base": "https://example.invalid",
            }
        ),
        encoding="utf-8",
    )

    cfg = load_telegram_config(cfg_path)

    assert cfg == TelegramConfig(
        mode="test",
        bot_token="token",
        chat_id="chat",
        api_base="https://example.invalid",
    )


def test_load_telegram_config_defaults_to_disabled_when_missing() -> None:
    cfg = load_telegram_config(Path("/tmp/does-not-exist-telegram-config.json"))

    assert cfg.mode == "disabled"
    assert cfg.bot_token == ""
    assert cfg.chat_id == ""


def test_format_alert_message_includes_test_prefix() -> None:
    text = format_alert_message(_candidate(), test_prefix=True)

    assert text.startswith("TEST: SPY state changed")
    assert "SPY changed from clean to DMG." in text
    assert "Symbol: SPY" in text
    assert "Severity: warning" in text


def test_disabled_mode_does_not_send() -> None:
    sender = Mock()

    result = send_alert_candidate(
        _candidate(),
        config=TelegramConfig(mode="disabled"),
        sender=sender,
    )

    assert result.delivery_status == "disabled"
    assert result.sent is False
    sender.assert_not_called()


def test_dry_run_mode_does_not_send() -> None:
    sender = Mock()

    result = send_alert_candidate(
        _candidate(),
        config=TelegramConfig(mode="dry-run", bot_token="token", chat_id="chat"),
        sender=sender,
    )

    assert result.delivery_status == "dry-run"
    assert result.sent is False
    assert "SPY state changed" in result.text
    sender.assert_not_called()


def test_test_mode_sends_with_test_prefix() -> None:
    sender = Mock()
    response = Mock()
    sender.return_value = response

    result = send_alert_candidate(
        _candidate(),
        config=TelegramConfig(
            mode="test",
            bot_token="token",
            chat_id="chat",
            api_base="https://api.example",
        ),
        sender=sender,
        now_utc="2026-05-01T15:00:00Z",
    )

    assert result.delivery_status == "sent"
    assert result.sent is True
    assert result.delivered_at_utc == "2026-05-01T15:00:00Z"
    sender.assert_called_once()
    url, data, timeout = sender.call_args.args
    assert url == "https://api.example/bottoken/sendMessage"
    assert data["chat_id"] == "chat"
    assert data["text"].startswith("TEST: SPY state changed")
    assert timeout == 10
    response.raise_for_status.assert_called_once_with()


def test_live_mode_sends_without_test_prefix() -> None:
    sender = Mock()
    response = Mock()
    sender.return_value = response

    result = send_alert_candidate(
        _candidate(),
        config=TelegramConfig(
            mode="live",
            bot_token="token",
            chat_id="chat",
            api_base="https://api.example",
        ),
        sender=sender,
    )

    assert result.delivery_status == "sent"
    assert result.sent is True
    data = sender.call_args.args[1]
    assert data["text"].startswith("SPY state changed")
    assert not data["text"].startswith("TEST:")


def test_test_or_live_mode_requires_credentials() -> None:
    sender = Mock()

    result = send_alert_candidate(
        _candidate(),
        config=TelegramConfig(mode="live"),
        sender=sender,
    )

    assert result.delivery_status == "error"
    assert result.sent is False
    assert result.error_text == "missing telegram bot_token or chat_id"
    sender.assert_not_called()


def test_send_error_is_returned_without_raising() -> None:
    def sender(_url, _data, _timeout):
        raise RuntimeError("network down")

    result = send_alert_candidate(
        _candidate(),
        config=TelegramConfig(mode="live", bot_token="token", chat_id="chat"),
        sender=sender,
    )

    assert result.delivery_status == "error"
    assert result.sent is False
    assert result.error_text == "network down"


def test_send_and_record_alert_candidate_writes_sqlite_status(tmp_path: Path) -> None:
    db = tmp_path / "market_health_alerts.v1.sqlite"
    run_id = start_run(db_path=db, mode="dry-run", trigger_name="manual")

    result = send_and_record_alert_candidate(
        db_path=db,
        run_id=run_id,
        candidate=_candidate(),
        config=TelegramConfig(mode="dry-run", bot_token="token", chat_id="chat"),
        sender=Mock(),
        ts_utc="2026-05-01T15:00:00Z",
    )

    assert result.delivery_status == "dry-run"

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        """
        SELECT alert_key, delivery_status, delivered_at_utc, error_text, payload_json
        FROM alerts
        """
    ).fetchone()
    conn.close()

    assert row[0] == "position_state:SPY:clean->DMG"
    assert row[1] == "dry-run"
    assert row[2] is None
    assert row[3] is None
    payload = json.loads(row[4])
    assert payload["from"] == "clean"
    assert "telegram_text" in payload


def test_send_and_record_alert_candidate_records_send_error(tmp_path: Path) -> None:
    db = tmp_path / "market_health_alerts.v1.sqlite"
    run_id = start_run(db_path=db, mode="live", trigger_name="manual")

    def sender(_url, _data, _timeout):
        raise RuntimeError("network down")

    result = send_and_record_alert_candidate(
        db_path=db,
        run_id=run_id,
        candidate=_candidate(),
        config=TelegramConfig(mode="live", bot_token="token", chat_id="chat"),
        sender=sender,
        ts_utc="2026-05-01T15:00:00Z",
    )

    assert result.delivery_status == "error"

    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT delivery_status, error_text FROM alerts").fetchone()
    conn.close()

    assert row == ("error", "network down")
