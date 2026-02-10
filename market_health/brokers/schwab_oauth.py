from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/jerboa/schwab_oauth.json")
DEFAULT_TOKEN_PATH = os.path.expanduser("~/.cache/jerboa/schwab.token.json")


@dataclass(frozen=True)
class SchwabOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    auth_url: str
    token_url: str
    scope: str = ""


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> SchwabOAuthConfig:
    p = os.path.expanduser(path)
    d = _read_json(p)
    missing = [k for k in ("client_id", "client_secret", "redirect_uri", "auth_url", "token_url") if not d.get(k)]
    if missing:
        raise ValueError(f"Missing required config keys in {p}: {', '.join(missing)}")
    return SchwabOAuthConfig(
        client_id=str(d["client_id"]),
        client_secret=str(d["client_secret"]),
        redirect_uri=str(d["redirect_uri"]),
        auth_url=str(d["auth_url"]),
        token_url=str(d["token_url"]),
        scope=str(d.get("scope", "")),
    )


def build_authorize_url(cfg: SchwabOAuthConfig, state: str = "mh") -> str:
    q = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "state": state,
    }
    if cfg.scope:
        q["scope"] = cfg.scope
    return cfg.auth_url + ("&" if "?" in cfg.auth_url else "?") + urllib.parse.urlencode(q)


def token_is_fresh(token: Dict[str, Any], leeway_sec: int = 60) -> bool:
    exp = token.get("expires_at")
    if not isinstance(exp, (int, float)):
        return False
    return time.time() < float(exp) - float(leeway_sec)


def load_token(path: str = DEFAULT_TOKEN_PATH) -> Optional[Dict[str, Any]]:
    p = os.path.expanduser(path)
    if not os.path.exists(p):
        return None
    return _read_json(p)


def _oauth_post(token_url: str, data: Dict[str, str]) -> Dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def exchange_code_for_token(
    cfg: SchwabOAuthConfig,
    code: str,
    token_path: str = DEFAULT_TOKEN_PATH,
) -> Dict[str, Any]:
    resp = _oauth_post(
        cfg.token_url,
        {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": cfg.redirect_uri,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        },
    )
    if "expires_in" in resp and "expires_at" not in resp:
        try:
            resp["expires_at"] = int(time.time() + int(resp["expires_in"]))
        except Exception:
            pass
    _write_json(os.path.expanduser(token_path), resp)
    return resp


def refresh_access_token(
    cfg: SchwabOAuthConfig,
    token: Dict[str, Any],
    token_path: str = DEFAULT_TOKEN_PATH,
) -> Dict[str, Any]:
    rt = token.get("refresh_token")
    if not rt:
        raise ValueError("No refresh_token present; re-authorize to obtain tokens.")
    resp = _oauth_post(
        cfg.token_url,
        {
            "grant_type": "refresh_token",
            "refresh_token": str(rt),
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        },
    )
    if "refresh_token" not in resp:
        resp["refresh_token"] = rt
    if "expires_in" in resp and "expires_at" not in resp:
        try:
            resp["expires_at"] = int(time.time() + int(resp["expires_in"]))
        except Exception:
            pass
    _write_json(os.path.expanduser(token_path), resp)
    return resp


def get_access_token(
    config_path: str = DEFAULT_CONFIG_PATH,
    token_path: str = DEFAULT_TOKEN_PATH,
) -> Tuple[str, Dict[str, Any]]:
    cfg = load_config(config_path)
    tok = load_token(token_path)
    if tok and token_is_fresh(tok):
        return str(tok.get("access_token", "")), tok
    if tok:
        tok = refresh_access_token(cfg, tok, token_path=token_path)
        return str(tok.get("access_token", "")), tok
    raise FileNotFoundError(
        f"No token found at {os.path.expanduser(token_path)}. Run authorize flow first."
    )
