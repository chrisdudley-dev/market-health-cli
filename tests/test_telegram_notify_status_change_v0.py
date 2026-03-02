import json
from pathlib import Path
from unittest.mock import Mock

import scripts.telegram_notify_on_status_change_v0 as mod


def _write_contract(
    p: Path, *, status: str | None = None, status_line: str | None = None
) -> None:
    doc: dict = {
        "schema": "jerboa.market_health.ui.v1",
        "asof": "2026-02-23T00:00:00Z",
        "meta": {},
        "summary": {},
        "data": {},
    }
    if status is not None:
        doc["data"]["state"] = {"status": status}
    if status_line is not None:
        doc["status_line"] = status_line
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


def _read_state(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_initialize_writes_state_no_send(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    contract = tmp_path / ".cache" / "jerboa" / "market_health.ui.v1.json"
    state = (
        tmp_path / ".cache" / "jerboa" / "state" / "market_health_ui.last_status.json"
    )
    cfg = tmp_path / ".config" / "jerboa" / "telegram.json"

    _write_contract(contract, status="OK")

    # even if config exists, first run should not send
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"bot_token": "t", "chat_id": "c"}), encoding="utf-8")

    post = Mock()
    monkeypatch.setattr(mod.requests, "post", post)

    assert mod.main([]) == 0
    assert state.exists()
    assert _read_state(state)["status_key"] == "OK"
    post.assert_not_called()


def test_change_sends_once_and_updates_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    contract = tmp_path / ".cache" / "jerboa" / "market_health.ui.v1.json"
    state = (
        tmp_path / ".cache" / "jerboa" / "state" / "market_health_ui.last_status.json"
    )
    cfg = tmp_path / ".config" / "jerboa" / "telegram.json"

    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"bot_token": "t", "chat_id": "c"}), encoding="utf-8")

    # init
    _write_contract(contract, status="OK")
    post = Mock()
    resp = Mock()
    resp.status_code = 200
    resp.text = "ok"
    post.return_value = resp
    monkeypatch.setattr(mod.requests, "post", post)
    mod.main([])
    post.assert_not_called()

    # change
    _write_contract(contract, status="WARN")
    mod.main([])
    assert post.call_count == 1
    assert _read_state(state)["status_key"] == "WARN"


def test_fallback_to_status_line(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    contract = tmp_path / ".cache" / "jerboa" / "market_health.ui.v1.json"
    state = (
        tmp_path / ".cache" / "jerboa" / "state" / "market_health_ui.last_status.json"
    )
    cfg = tmp_path / ".config" / "jerboa" / "telegram.json"

    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"bot_token": "t", "chat_id": "c"}), encoding="utf-8")

    _write_contract(contract, status_line="STATUS: OK")
    post = Mock()
    resp = Mock()
    resp.status_code = 200
    resp.text = "ok"
    post.return_value = resp
    monkeypatch.setattr(mod.requests, "post", post)

    mod.main([])  # init no send
    assert _read_state(state)["status_key"] == "STATUS: OK"

    _write_contract(contract, status_line="STATUS: WARN")
    mod.main([])
    assert post.call_count == 1
