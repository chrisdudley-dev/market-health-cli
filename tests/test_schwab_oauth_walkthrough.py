from pathlib import Path


SCRIPT = Path("scripts/schwab_oauth_walkthrough.py")


def test_walkthrough_writes_actual_token_cache_not_marker_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "token exchange complete (tokens not stored)" not in text
    assert "tok_disk = dict(tok)" in text
    assert "json.dumps(obj" in text
    assert "os.chmod(p, 0o600)" in text
    assert "secrets not printed" in text


def test_walkthrough_redacts_tokens_for_display_helpers() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "def _sanitize_for_display" in text
    assert '"access_token"' in text
    assert '"refresh_token"' in text
    assert 'out[k] = "***"' in text
