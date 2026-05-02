from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/schwab_oauth_cli.py")


def test_init_config_writes_template_with_private_permissions(tmp_path: Path) -> None:
    config = tmp_path / "schwab_oauth.json"
    token = tmp_path / "schwab.token.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(config),
            "--token",
            str(token),
            "--init-config",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0
    assert "OK: wrote config template" in proc.stdout
    assert "secrets were not printed" in proc.stdout
    assert config.exists()

    text = config.read_text(encoding="utf-8")
    assert "client_id" in text
    assert "client_secret" in text
    assert "token_url" in text
    assert oct(config.stat().st_mode & 0o777) == "0o600"


def test_init_config_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = tmp_path / "schwab_oauth.json"
    config.write_text('{"client_id":"keep"}\n', encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(config),
            "--init-config",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 2
    assert "config already exists" in proc.stderr
    assert config.read_text(encoding="utf-8") == '{"client_id":"keep"}\n'
