#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import os
import sys

# Allow running from repo checkout without installing the package
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parents[1]
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

    if args.status:
        tok = load_token(tok_path)
        if not tok:
            print(f"NO TOKEN: {tok_path}")
            return 0
        fresh = token_is_fresh(tok)
        print(f"TOKEN: {tok_path}")
        print(f"fresh={fresh} expires_at={tok.get('expires_at', '?')}")
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
    print(
        f"OK: access_token present (len={len(access)}) expires_at={tok.get('expires_at', '?')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
