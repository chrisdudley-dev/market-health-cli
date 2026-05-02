from __future__ import annotations

import json
from pathlib import Path


EXAMPLE = Path("docs/examples/schwab_oauth.json.example")


def test_schwab_oauth_example_has_default_provider_urls() -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    assert data["client_id"] == "REPLACE_ME"
    assert data["client_secret"] == "REPLACE_ME"
    assert data["auth_url"] == "https://api.schwabapi.com/v1/oauth/authorize"
    assert data["token_url"] == "https://api.schwabapi.com/v1/oauth/token"
    assert data["redirect_uri"]
