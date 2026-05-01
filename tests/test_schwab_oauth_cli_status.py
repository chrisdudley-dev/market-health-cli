from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/schwab_oauth_cli.py")


def run_status(config: Path, token: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(config),
            "--token",
            str(token),
            "--status",
        ],
        check=False,
        text=True,
        capture_output=True,
    )


def test_status_reports_missing_config_and_token_without_error(tmp_path: Path) -> None:
    config = tmp_path / "missing_config.json"
    token = tmp_path / "missing_token.json"

    proc = run_status(config, token)

    assert proc.returncode == 0
    assert f"CONFIG: {config}" in proc.stdout
    assert "config_exists=False" in proc.stdout
    assert "config_missing=missing_file" in proc.stdout
    assert f"TOKEN: {token}" in proc.stdout
    assert "token_exists=False" in proc.stdout


def test_status_reports_presence_without_printing_secret_values(tmp_path: Path) -> None:
    config = tmp_path / "schwab_oauth.json"
    token = tmp_path / "schwab.token.json"

    config.write_text(
        json.dumps(
            {
                "client_id": "CLIENT_VALUE_SHOULD_NOT_PRINT",
                "client_secret": "SECRET_VALUE_SHOULD_NOT_PRINT",
                "redirect_uri": "https://127.0.0.1/callback",
                "auth_url": "https://auth.example/authorize",
                "token_url": "https://auth.example/token",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    token.write_text(
        json.dumps(
            {
                "access_token": "ACCESS_VALUE_SHOULD_NOT_PRINT",
                "refresh_token": "REFRESH_VALUE_SHOULD_NOT_PRINT",
                "expires_at": 9999999999,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    proc = run_status(config, token)

    assert proc.returncode == 0
    assert "config_exists=True" in proc.stdout
    assert "config_missing=" in proc.stdout
    assert "token_exists=True" in proc.stdout
    assert "has_access_token=True" in proc.stdout
    assert "has_refresh_token=True" in proc.stdout
    assert "CLIENT_VALUE_SHOULD_NOT_PRINT" not in proc.stdout
    assert "SECRET_VALUE_SHOULD_NOT_PRINT" not in proc.stdout
    assert "ACCESS_VALUE_SHOULD_NOT_PRINT" not in proc.stdout
    assert "REFRESH_VALUE_SHOULD_NOT_PRINT" not in proc.stdout
