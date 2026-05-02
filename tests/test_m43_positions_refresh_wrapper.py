from pathlib import Path


WRAPPER = Path("scripts/jerboa/bin/jerboa-market-health-positions-refresh")


def test_positions_refresh_reports_safe_schwab_status_hint() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "print_schwab_setup_hint" in text
    assert "Schwab OAuth status:" in text
    assert "scripts/schwab_oauth_cli.py" in text
    assert "--status" in text
    assert "JERBOA_POSITIONS_HIDE_SCHWAB_HINT" in text
    assert "SCHWAB_CONFIG_FILE" in text
    assert "TOKEN_FILE" in text
