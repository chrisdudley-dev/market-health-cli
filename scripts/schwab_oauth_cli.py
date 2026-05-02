#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

# Allow running from repo checkout without installing the package
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLE_CONFIG_PATH = (
    _REPO_ROOT / "docs" / "examples" / "schwab_oauth.json.example"
)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from market_health.brokers.schwab_oauth import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_TOKEN_PATH,
    build_authorize_url,
    exchange_code_for_token,
    get_access_token,
    load_config,
    load_token,
    refresh_access_token,
    token_is_fresh,
)


def _looks_like_placeholder(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True

    placeholder_markers = (
        "replace",
        "your_",
        "your-",
        "todo",
        "example",
        "placeholder",
        "changeme",
        "change_me",
        "<",
        ">",
    )
    return any(marker in text for marker in placeholder_markers)


def _config_status(path: str) -> tuple[bool, list[str]]:
    cfg_path = os.path.expanduser(path)
    if not os.path.exists(cfg_path):
        return False, ["missing_file"]

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return True, ["unreadable_json"]

    required = ["client_id", "client_secret", "redirect_uri", "auth_url", "token_url"]
    missing = [key for key in required if _looks_like_placeholder(data.get(key))]
    return True, missing


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Schwab OAuth helper (local-only secrets + token cache)"
    )
    ap.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH, help="Path to local OAuth config JSON"
    )
    ap.add_argument(
        "--token", default=DEFAULT_TOKEN_PATH, help="Path to local token JSON cache"
    )
    ap.add_argument(
        "--status", action="store_true", help="Show token status (no network calls)"
    )
    ap.add_argument(
        "--init-config",
        action="store_true",
        help="Create a local Schwab OAuth config template with 0600 permissions",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Allow --init-config to overwrite an existing config file",
    )
    ap.add_argument(
        "--print-auth-url", action="store_true", help="Print the authorize URL"
    )
    ap.add_argument(
        "--exchange-code",
        default="",
        help="Exchange authorization code for tokens (network call)",
    )
    ap.add_argument(
        "--refresh", action="store_true", help="Refresh token now (network call)"
    )
    args = ap.parse_args()

    cfg_path = os.path.expanduser(args.config)
    tok_path = os.path.expanduser(args.token)

    if args.init_config:
        dst = _Path(cfg_path)
        if dst.exists() and not args.force:
            print(f"ERR: config already exists: {dst}", file=sys.stderr)
            print("Use --force to overwrite it.", file=sys.stderr)
            return 2

        if not DEFAULT_EXAMPLE_CONFIG_PATH.exists():
            print(
                f"ERR: example config missing: {DEFAULT_EXAMPLE_CONFIG_PATH}",
                file=sys.stderr,
            )
            return 2

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_EXAMPLE_CONFIG_PATH, dst)
        try:
            os.chmod(dst, 0o600)
        except Exception:
            pass

        print(f"OK: wrote config template: {dst}")
        print("Fill in client_id and client_secret locally; secrets were not printed.")
        return 0

    if args.status:
        cfg_exists, cfg_missing = _config_status(cfg_path)
        print(f"CONFIG: {cfg_path}")
        print(f"config_exists={cfg_exists}")
        print("config_missing=" + ",".join(cfg_missing))

        tok = load_token(tok_path)
        print(f"TOKEN: {tok_path}")
        if not tok:
            print("token_exists=False")
            return 0

        fresh = token_is_fresh(tok)
        print("token_exists=True")
        print(f"fresh={fresh} expires_at={tok.get('expires_at', '?')}")
        print(f"has_access_token={bool(str(tok.get('access_token', '')).strip())}")
        print(f"has_refresh_token={bool(str(tok.get('refresh_token', '')).strip())}")
        return 0

    try:
        cfg = load_config(cfg_path)
    except Exception as e:
        print(f"ERR: config not ready at {cfg_path}: {e}", file=sys.stderr)
        print(
            "Hint: copy docs/examples/schwab_oauth.json.example to ~/.config/jerboa/schwab_oauth.json and fill it in.",
            file=sys.stderr,
        )
        return 2

    if args.print_auth_url:
        print(build_authorize_url(cfg))
        return 0

    if args.exchange_code:
        exchange_code_for_token(cfg, args.exchange_code, token_path=tok_path)
        print(f"OK: wrote token cache: {tok_path}")
        return 0

    if args.refresh:
        tok = load_token(tok_path)
        if not tok:
            print(f"ERR: no token to refresh at {tok_path}", file=sys.stderr)
            return 2
        refresh_access_token(cfg, tok, token_path=tok_path)
        print(f"OK: refreshed token cache: {tok_path}")
        return 0

    try:
        access, tok = get_access_token(cfg_path, tok_path)
    except Exception as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 2
    print("OK: access token present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
