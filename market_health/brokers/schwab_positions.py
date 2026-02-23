from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_float(x: Any) -> Optional[float]:
    if isinstance(x, (int, float)):
        return float(x)
    try:
        if isinstance(x, str) and x.strip():
            return float(x)
    except Exception:
        return None
    return None


def _as_str(x: Any) -> str:
    return str(x) if x is not None else ""


def _find_positions_lists(obj: Any, max_depth: int = 8) -> List[List[Dict[str, Any]]]:
    found: List[List[Dict[str, Any]]] = []
    seen: set[int] = set()

    def walk(x: Any, depth: int) -> None:
        if depth > max_depth:
            return
        xid = id(x)
        if xid in seen:
            return
        seen.add(xid)

        if isinstance(x, dict):
            for k, v in x.items():
                # common key
                if (
                    isinstance(k, str)
                    and k.lower() == "positions"
                    and isinstance(v, list)
                ):
                    if v and all(isinstance(it, dict) for it in v):
                        found.append(v)  # candidate
                walk(v, depth + 1)
        elif isinstance(x, list):
            for it in x:
                walk(it, depth + 1)

    walk(obj, 0)
    return found


_OPT_SYM_RE = re.compile(r"^([A-Z]+)_(\d{6})([CP])(\d+(?:\.\d+)?)$", re.ASCII)


def _parse_option_symbol(
    sym: str,
) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[str]]:
    """
    Try to parse simple option sym like SPY_020725C500 -> underlying, expiry(YYYY-MM-DD), strike, right
    """
    m = _OPT_SYM_RE.match(sym.strip().upper())
    if not m:
        return None, None, None, None
    underlying, mmddyy, right, strike_s = m.groups()
    mm = int(mmddyy[0:2])
    dd = int(mmddyy[2:4])
    yy = int(mmddyy[4:6])
    yyyy = 2000 + yy
    expiry = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    try:
        strike = float(strike_s)
    except Exception:
        strike = None
    return underlying, expiry, strike, right


def _infer_asset_type(pos: Dict[str, Any]) -> str:
    inst = pos.get("instrument") or pos.get("Instrument") or {}
    at = _as_str(inst.get("assetType") or pos.get("assetType")).strip().upper()
    if "OPTION" in at or at.startswith("OPT"):
        return "option"
    if at in ("EQUITY", "ETF", "STOCK"):
        return "equity"
    # fallback: try symbol pattern
    sym = _as_str(inst.get("symbol") or pos.get("symbol")).strip().upper()
    if _OPT_SYM_RE.match(sym):
        return "option"
    return "other"


def _qty(pos: Dict[str, Any]) -> Optional[float]:
    q = _as_float(pos.get("quantity"))
    if q is not None:
        return q
    long_q = _as_float(pos.get("longQuantity"))
    short_q = _as_float(pos.get("shortQuantity"))
    if long_q is not None and short_q is not None:
        return float(long_q) - float(short_q)
    if long_q is not None:
        return float(long_q)
    return _as_float(pos.get("qty"))


def normalize_schwab_accounts_json(raw: Any, source_path: str = "") -> Dict[str, Any]:
    # Prefer account-aware extraction when raw is a list of account payloads.
    acct_positions: List[Tuple[str, str, Dict[str, Any]]] = []
    if isinstance(raw, list) and raw and all(isinstance(x, dict) for x in raw):
        for acct in raw:
            sa = acct.get("securitiesAccount") or acct.get("SecuritiesAccount") or {}
            if not isinstance(sa, dict):
                continue

            acct_id = _as_str(
                sa.get("accountId")
                or sa.get("hashValue")
                or sa.get("accountNumberLast4")
                or sa.get("accountNumber")
                or ""
            ).strip()

            last4 = _as_str(sa.get("accountNumberLast4") or "").strip()
            if not last4:
                an = _as_str(sa.get("accountNumber") or "").strip()
                if len(an) >= 4:
                    last4 = an[-4:]

            acct_label = _as_str(
                sa.get("accountType") or sa.get("nickname") or ""
            ).strip()
            if not acct_label and last4:
                acct_label = f"Schwab ****{last4}"
            elif not acct_label and acct_id:
                acct_label = f"Schwab {acct_id[:6]}…"

            plist = sa.get("positions") or sa.get("Positions") or []
            if isinstance(plist, list):
                for p in plist:
                    if isinstance(p, dict):
                        acct_positions.append((acct_id, acct_label, p))

    # Fallback: find positions lists anywhere in the payload (loses account context)
    if not acct_positions:
        lists = _find_positions_lists(raw)
        for lst in lists:
            for p in lst:
                if isinstance(p, dict):
                    acct_positions.append(("", "", p))

    # De-dupe by (account, symbol, qty, avg, mv) to reduce repeats while preserving multi-account holdings.
    dedup: Dict[Tuple[str, str, str, str, str], Tuple[str, str, Dict[str, Any]]] = {}
    for acct_id, acct_label, p in acct_positions:
        inst = p.get("instrument") or {}
        sym = _as_str(inst.get("symbol") or p.get("symbol")).strip()
        key = (
            acct_id,
            sym,
            _as_str(p.get("longQuantity") or p.get("quantity") or ""),
            _as_str(p.get("averagePrice") or ""),
            _as_str(p.get("marketValue") or ""),
        )
        if sym:
            dedup[key] = (acct_id, acct_label, p)

    acct_positions = list(dedup.values())

    out_positions: List[Dict[str, Any]] = []

    for acct_id, acct_label, p in acct_positions:
        inst = p.get("instrument") or p.get("Instrument") or {}
        sym = _as_str(inst.get("symbol") or p.get("symbol")).strip()
        if not sym:
            continue

        asset_type = _infer_asset_type(p)
        qty = _qty(p)
        avg = _as_float(p.get("averagePrice") or p.get("avgPrice"))
        mv = _as_float(p.get("marketValue") or p.get("market_value"))
        mark = _as_float(p.get("mark") or inst.get("mark"))

        if mark is None and mv is not None and qty not in (None, 0):
            try:
                mark = float(mv) / float(qty)
            except Exception:
                mark = None

        item: Dict[str, Any] = {
            "asset_type": asset_type,
            "symbol": sym,
        }
        if acct_id:
            item["account_id"] = acct_id
        if acct_label:
            item["account_label"] = acct_label
        if qty is not None:
            item["qty"] = qty
        if avg is not None:
            item["avg_price"] = avg
        if mark is not None:
            item["mark_price"] = mark
        if mv is not None:
            item["market_value"] = mv

        # option fields (best effort)
        if asset_type == "option":
            underlying = _as_str(
                inst.get("underlyingSymbol")
                or inst.get("underlying")
                or p.get("underlying")
            ).strip()
            expiry = _as_str(
                inst.get("optionExpirationDate")
                or inst.get("expirationDate")
                or p.get("expiry")
            ).strip()
            strike = _as_float(
                inst.get("strikePrice") or inst.get("strike") or p.get("strike")
            )
            right_raw = (
                _as_str(inst.get("putCall") or inst.get("right")).strip().upper()
            )

            right = None
            if right_raw.startswith("C"):
                right = "C"
            elif right_raw.startswith("P"):
                right = "P"

            # parse from symbol if still missing
            if not underlying or not expiry or strike is None or right is None:
                u2, e2, k2, r2 = _parse_option_symbol(sym)
                underlying = underlying or (u2 or "")
                expiry = expiry or (e2 or "")
                strike = strike if strike is not None else k2
                right = right or r2

            if underlying:
                item["underlying"] = underlying
            if expiry:
                item["expiry"] = expiry
            if strike is not None:
                item["strike"] = strike
            if right in ("C", "P"):
                item["right"] = right

        out_positions.append(item)

    summary = {
        "count": len(out_positions),
        "equities": sum(1 for x in out_positions if x.get("asset_type") == "equity"),
        "options": sum(1 for x in out_positions if x.get("asset_type") == "option"),
    }

    return {
        "schema": "positions.v1",
        "generated_at": _iso_now(),
        "source": {
            "type": "schwab",
            "path": os.path.expanduser(source_path) if source_path else "",
            "note": "Normalized from saved Schwab accounts/positions JSON (offline).",
        },
        "summary": summary,
        "positions": out_positions,
    }


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
