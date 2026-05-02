from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


SCRIPT = Path("scripts/schwab_oauth_walkthrough.py")


def load_walkthrough_module() -> ModuleType:
    name = "schwab_oauth_walkthrough"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_load_cfg_creates_first_run_config_without_printing_secrets(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = load_walkthrough_module()
    config = tmp_path / "schwab_oauth.json"

    monkeypatch.setattr(module, "_prompt_text", lambda prompt: "CLIENT_ID_VALUE")
    monkeypatch.setattr(module, "_prompt_secret", lambda prompt: "CLIENT_SECRET_VALUE")

    cfg = module.load_cfg(str(config))
    captured = capsys.readouterr()

    assert cfg.client_id == "CLIENT_ID_VALUE"
    assert cfg.client_secret == "CLIENT_SECRET_VALUE"
    assert cfg.redirect_uri == "http://127.0.0.1:8080/callback"
    assert cfg.auth_url == "https://api.schwabapi.com/v1/oauth/authorize"
    assert cfg.token_url == "https://api.schwabapi.com/v1/oauth/token"
    assert "secrets not printed" in captured.out
    assert "CLIENT_SECRET_VALUE" not in captured.out
    assert oct(config.stat().st_mode & 0o777) == "0o600"

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["client_id"] == "CLIENT_ID_VALUE"
    assert data["client_secret"] == "CLIENT_SECRET_VALUE"


def test_load_cfg_replaces_template_placeholders(tmp_path: Path, monkeypatch) -> None:
    module = load_walkthrough_module()
    config = tmp_path / "schwab_oauth.json"
    config.write_text(
        json.dumps(
            {
                "client_id": "REPLACE_ME",
                "client_secret": "REPLACE_ME",
                "redirect_uri": "http://127.0.0.1:8080/callback",
                "auth_url": "https://api.schwabapi.com/v1/oauth/authorize",
                "token_url": "https://api.schwabapi.com/v1/oauth/token",
                "scope": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_prompt_text", lambda prompt: "CLIENT_ID_VALUE")
    monkeypatch.setattr(module, "_prompt_secret", lambda prompt: "CLIENT_SECRET_VALUE")

    cfg = module.load_cfg(str(config))

    assert cfg.client_id == "CLIENT_ID_VALUE"
    assert cfg.client_secret == "CLIENT_SECRET_VALUE"
    assert cfg.auth_url == "https://api.schwabapi.com/v1/oauth/authorize"
    assert cfg.token_url == "https://api.schwabapi.com/v1/oauth/token"


def test_load_cfg_can_use_environment_credentials(tmp_path: Path, monkeypatch) -> None:
    module = load_walkthrough_module()
    config = tmp_path / "schwab_oauth.json"

    monkeypatch.setenv("SCHWAB_CLIENT_ID", "ENV_CLIENT_ID")
    monkeypatch.setenv("SCHWAB_CLIENT_SECRET", "ENV_CLIENT_SECRET")

    cfg = module.load_cfg(str(config))

    assert cfg.client_id == "ENV_CLIENT_ID"
    assert cfg.client_secret == "ENV_CLIENT_SECRET"
