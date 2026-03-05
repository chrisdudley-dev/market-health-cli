from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests  # tests monkeypatch mod.requests.post


def _cache_dir() -> Path:
    # tests monkeypatch HOME; expanduser respects it at runtime
    return Path(os.path.expanduser("~/.cache/jerboa"))


def _ui_contract_path() -> Path:
    return _cache_dir() / "market_health.ui.v1.json"


def _state_path() -> Path:
    # tests expect this exact filename
    return _cache_dir() / "state" / "market_health_ui.last_status.json"


def _cfg_path() -> Path:
    return Path(os.path.expanduser("~/.config/jerboa/telegram.json"))


def _read_json(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_atomic(p: Path, obj: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def _load_contract() -> dict[str, Any]:
    doc = _read_json(_ui_contract_path())
    return doc if isinstance(doc, dict) else {}


def _extract_status_key(contract: dict[str, Any]) -> str | None:
    """
    Matches tests:
      - Primary: contract.data.state.status  (e.g. "OK", "WARN")
      - Fallback: contract.status_line       (e.g. "STATUS: OK")
    """
    data = contract.get("data")
    if isinstance(data, dict):
        state = data.get("state")
        if isinstance(state, dict):
            s = state.get("status")
            if isinstance(s, str) and s.strip():
                return s.strip()

    sl = contract.get("status_line")
    if isinstance(sl, str) and sl.strip():
        return sl.strip()

    return None


def _load_prev_status_key() -> str | None:
    st = _read_json(_state_path())
    v = st.get("status_key")
    return v.strip() if isinstance(v, str) and v.strip() else None


def _write_status_key(status_key: str) -> None:
    # tests assert key name == "status_key"
    _write_json_atomic(_state_path(), {"status_key": status_key})


def _load_telegram_cfg() -> tuple[str, str] | None:
    cfg = _read_json(_cfg_path())
    token = cfg.get("bot_token")
    chat_id = cfg.get("chat_id")
    if isinstance(token, str) and token.strip() and isinstance(chat_id, str) and chat_id.strip():
        return token.strip(), chat_id.strip()
    return None


def _send(token: str, chat_id: str, text: str) -> None:
    # tests only assert that requests.post is called; payload details can be minimal
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)


def main(argv: list[str] | None = None) -> int:
    _ = argv  # tests call main([])

    contract = _load_contract()
    curr = _extract_status_key(contract)
    if curr is None:
        return 0

    prev = _load_prev_status_key()

    # First run: write state, do NOT send (even if cfg exists)
    if prev is None:
        _write_status_key(curr)
        return 0

    # No change: do nothing
    if prev.strip() == curr.strip():
        return 0

    cfg = _load_telegram_cfg()
    if cfg is not None:
        token, chat_id = cfg
        _send(token, chat_id, f"Market Health status changed: {prev} -> {curr}")

    # Always update state on change (prevents repeat notifications)
    _write_status_key(curr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
