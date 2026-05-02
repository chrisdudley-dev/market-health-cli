#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import getpass


DEFAULT_REDIRECT_URI = "http://127.0.0.1:8080/callback"
DEFAULT_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
DEFAULT_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


def _sanitize_for_display(obj):
    """Return a redacted copy suitable for logs/stdout."""
    if not isinstance(obj, dict):
        return obj
    out = dict(obj)
    for k in (
        "client_secret",
        "password",
        "access_token",
        "refresh_token",
        "id_token",
    ):
        if k in out:
            out[k] = "***"
    return out


@dataclass(frozen=True)
class Cfg:
    client_id: str
    client_secret: str
    redirect_uri: str
    auth_url: str
    token_url: str
    scope: str = ""


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


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


def _prompt_text(prompt: str) -> str:
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            tty.write(prompt)
            tty.flush()
            return tty.readline().strip()
    except OSError:
        return input(prompt).strip()


def _prompt_secret(prompt: str) -> str:
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            return getpass.getpass(prompt, stream=tty).strip()
    except OSError:
        return getpass.getpass(prompt).strip()


def _write_json_secure(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


def _chmod_dir_private(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except Exception:
        pass


def load_cfg(path: str) -> Cfg:
    p = Path(os.path.expanduser(path))
    if p.exists():
        d = _read_json(p)
    else:
        d = {}

    changed = False

    if _looks_like_placeholder(d.get("client_id")):
        env_client_id = os.environ.get("SCHWAB_CLIENT_ID", "").strip()
        d["client_id"] = env_client_id or _prompt_text("SCHWAB_CLIENT_ID: ")
        changed = True

    if _looks_like_placeholder(d.get("client_secret")):
        env_client_secret = os.environ.get("SCHWAB_CLIENT_SECRET", "").strip()
        d["client_secret"] = env_client_secret or _prompt_secret(
            "SCHWAB_CLIENT_SECRET: "
        )
        changed = True

    defaults = {
        "redirect_uri": DEFAULT_REDIRECT_URI,
        "auth_url": DEFAULT_AUTH_URL,
        "token_url": DEFAULT_TOKEN_URL,
        "scope": "",
    }
    for key, default in defaults.items():
        if _looks_like_placeholder(d.get(key)):
            d[key] = default
            changed = True

    need = ["client_id", "client_secret", "redirect_uri", "auth_url", "token_url"]
    missing = [k for k in need if _looks_like_placeholder(d.get(k))]
    if missing:
        raise SystemExit(f"ERR: missing keys in {p}: {', '.join(missing)}")

    if changed or not p.exists():
        _write_json_secure(p, d)
        print(f"OK: wrote OAuth config -> {p} (0600; secrets not printed)")

    return Cfg(
        client_id=str(d["client_id"]),
        client_secret=str(d["client_secret"]),
        redirect_uri=str(d["redirect_uri"]),
        auth_url=str(d["auth_url"]),
        token_url=str(d["token_url"]),
        scope=str(d.get("scope", "")),
    )


def build_authorize_url(cfg: Cfg, state: str = "mh") -> str:
    q = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "state": state,
    }
    if cfg.scope:
        q["scope"] = cfg.scope
    return (
        cfg.auth_url + ("&" if "?" in cfg.auth_url else "?") + urllib.parse.urlencode(q)
    )


def extract_code_from_redirect_url(url: str) -> str:
    u = urllib.parse.urlparse(url.strip())
    q = urllib.parse.parse_qs(u.query)
    code = q.get("code", [""])[0]
    if not code:
        raise SystemExit("ERR: no code= found in that URL")
    # Schwab codes may include URL-encoded characters (e.g. %40)
    return urllib.parse.unquote(code)


def oauth_token_post(cfg: Cfg, form: Dict[str, str]) -> Dict[str, Any]:
    # Schwab token endpoint: Basic base64(client_id:client_secret)
    basic = base64.b64encode(
        f"{cfg.client_id}:{cfg.client_secret}".encode("utf-8")
    ).decode("ascii")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {basic}",
        "Accept": "application/json",
    }
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        cfg.token_url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"ERR: token endpoint HTTP {e.code}: {err}")
    return json.loads(raw)


def token_is_fresh(tok: Dict[str, Any], leeway: int = 60) -> bool:
    exp = tok.get("expires_at")
    if not isinstance(exp, (int, float)):
        return False
    return time.time() < float(exp) - float(leeway)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Schwab OAuth walkthrough: first-run setup, browser authorization, token cache"
    )
    ap.add_argument(
        "--config",
        default="~/.config/jerboa/schwab_oauth.json",
        help="OAuth config JSON",
    )
    ap.add_argument(
        "--token",
        default="~/.cache/jerboa/schwab.token.json",
        help="Token cache JSON (written with 0600)",
    )
    ap.add_argument("--state", default="mh", help="OAuth state param")
    args = ap.parse_args()

    cfg = load_cfg(args.config)

    # ensure dirs exist with private perms
    _chmod_dir_private(Path(os.path.expanduser("~/.config/jerboa")))
    _chmod_dir_private(Path(os.path.expanduser("~/.cache/jerboa")))

    auth_url = build_authorize_url(cfg, state=args.state)
    print("\n1) Open this URL in a browser and complete login/consent:\n")
    print(auth_url)
    print(
        "\n2) After redirect, paste the FULL redirect URL here.\n"
        "   (Even if the page doesn't load, copy the URL from the address bar.)\n"
    )

    try:
        redirect_url = _prompt_text("Redirect URL: ")
    except KeyboardInterrupt:
        print("\nCanceled. No changes made.")
        return 130
    code = extract_code_from_redirect_url(redirect_url)

    tok = oauth_token_post(
        cfg,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.redirect_uri,
        },
    )

    # compute expires_at if needed
    if "expires_in" in tok and "expires_at" not in tok:
        try:
            tok["expires_at"] = int(time.time() + int(tok["expires_in"]))
        except Exception:
            pass

    token_path = Path(os.path.expanduser(args.token))
    tok_disk = dict(tok)
    _write_json_secure(token_path, tok_disk)
    print(f"OK: wrote token cache -> {token_path} (0600; secrets not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
