from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests


def _default_contract_path() -> Path:
    return Path.home() / ".cache" / "jerboa" / "market_health.ui.v1.json"


def _default_state_path() -> Path:
    return (
        Path.home()
        / ".cache"
        / "jerboa"
        / "state"
        / "market_health_ui.last_status.json"
    )


def _default_config_path() -> Path:
    return Path.home() / ".config" / "jerboa" / "telegram.json"


def _log(msg: str, *, quiet: bool) -> None:
    if quiet:
        return
    print(msg, file=sys.stderr)


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _derive_status_key(contract: dict[str, Any]) -> Optional[str]:
    # Prefer .data.state.status
    data = contract.get("data")
    if isinstance(data, dict):
        state = data.get("state")
        if isinstance(state, dict):
            status = state.get("status")
            if isinstance(status, str) and status.strip():
                return status.strip()

    # Fallback: .status_line at root (or occasionally under summary)
    status_line = contract.get("status_line")
    if isinstance(status_line, str) and status_line.strip():
        return status_line.strip()

    summary = contract.get("summary")
    if isinstance(summary, dict):
        status_line2 = summary.get("status_line")
        if isinstance(status_line2, str) and status_line2.strip():
            return status_line2.strip()

    return None


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    api_base: str = "https://api.telegram.org"


def _load_telegram_config(path: Path) -> Optional[TelegramConfig]:
    doc = _read_json(path)
    if not isinstance(doc, dict):
        return None

    token = doc.get("bot_token") or doc.get("token")
    chat_id = doc.get("chat_id")
    api_base = doc.get("api_base") or "https://api.telegram.org"

    if not isinstance(token, str) or not token.strip():
        return None
    if not isinstance(chat_id, (str, int)) or str(chat_id).strip() == "":
        return None
    if not isinstance(api_base, str) or not api_base.strip():
        api_base = "https://api.telegram.org"

    return TelegramConfig(
        bot_token=token.strip(), chat_id=str(chat_id).strip(), api_base=api_base.strip()
    )


def _send_telegram(*, cfg: TelegramConfig, text: str, quiet: bool) -> bool:
    url = f"{cfg.api_base.rstrip('/')}/bot{cfg.bot_token}/sendMessage"
    payload = {
        "chat_id": cfg.chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code >= 400:
            _log(f"telegram: HTTP {r.status_code}: {r.text[:300]}", quiet=quiet)
            return False
        return True
    except Exception as e:
        _log(f"telegram: failed to send: {e}", quiet=quiet)
        return False


def _build_message(*, old: Optional[str], new: str, contract: dict[str, Any]) -> str:
    asof = contract.get("asof")
    asof_s = asof if isinstance(asof, str) else ""
    if old is None:
        header = "Market Health UI status initialized"
    else:
        header = "Market Health UI status changed"

    lines = [header]
    if old is not None:
        lines.append(f"From: {old}")
    lines.append(f"To:   {new}")
    if asof_s:
        lines.append(f"As of: {asof_s}")
    return "\n".join(lines)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Send a Telegram message when market_health UI status changes.",
    )
    ap.add_argument(
        "--contract",
        type=Path,
        default=_default_contract_path(),
        help="Path to market_health.ui.v1.json",
    )
    ap.add_argument(
        "--state",
        type=Path,
        default=_default_state_path(),
        help="Path to last-status state file",
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to Telegram config json",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send Telegram, only update last status",
    )
    ap.add_argument("--quiet", action="store_true", help="Suppress logs")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    quiet = bool(args.quiet)

    # Never block refresh pipelines: always exit 0.
    contract_path: Path = args.contract
    state_path: Path = args.state
    config_path: Path = args.config

    contract = _read_json(contract_path)
    if not isinstance(contract, dict):
        _log(
            f"status-notify: contract missing/unreadable: {contract_path}", quiet=quiet
        )
        return 0

    status_key = _derive_status_key(contract)
    if not status_key:
        _log(
            "status-notify: could not derive status key (no .data.state.status or .status_line)",
            quiet=quiet,
        )
        return 0

    prev_doc = _read_json(state_path)
    prev_key: Optional[str] = None
    if isinstance(prev_doc, dict):
        pk = prev_doc.get("status_key")
        if isinstance(pk, str):
            prev_key = pk

    # Always write state on first run (initialize) or when unchanged.
    if prev_key is None:
        _write_json(
            state_path,
            {"schema": "market_health_ui.last_status.v1", "status_key": status_key},
        )
        _log(f"status-notify: initialized last status: {status_key}", quiet=quiet)
        return 0

    if prev_key == status_key:
        _log("status-notify: status unchanged", quiet=quiet)
        return 0

    # Status changed: send Telegram (unless dry-run)
    msg = _build_message(old=prev_key, new=status_key, contract=contract)

    if args.dry_run:
        _write_json(
            state_path,
            {"schema": "market_health_ui.last_status.v1", "status_key": status_key},
        )
        _log("status-notify: dry-run (no telegram). Updated last status.", quiet=quiet)
        _log(msg, quiet=quiet)
        return 0

    cfg = _load_telegram_config(config_path)
    if cfg is None:
        _log(f"status-notify: missing/invalid config: {config_path}", quiet=quiet)
        # Do NOT update state if we couldn't send (so next run can try again).
        return 0

    ok = _send_telegram(cfg=cfg, text=msg, quiet=quiet)
    if ok:
        _write_json(
            state_path,
            {"schema": "market_health_ui.last_status.v1", "status_key": status_key},
        )
        _log("status-notify: sent telegram + updated last status", quiet=quiet)
    # If send failed, do not update state (so we retry next time).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
