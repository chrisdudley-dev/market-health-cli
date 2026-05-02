#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re as _re
from pathlib import Path
from typing import Any, Dict, List, Union

from market_health.forecast_input_inventory import forecast_input_inventory


def _err(errors: List[str], msg: str) -> None:
    errors.append(msg)


def _is_iso_datetime(s: str) -> bool:
    # accept Z or offset; keep this lightweight
    return bool(_re.match(r"^\d{4}-\d{2}-\d{2}T", s))


def _as_int_key(k: Any) -> Union[int, None]:
    if isinstance(k, int):
        return k
    if isinstance(k, str) and k.isdigit():
        return int(k)
    return None


def validate(doc: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if doc.get("schema") != "forecast_scores.v1":
        _err(errors, 'schema must be "forecast_scores.v1"')

    asof = doc.get("asof")
    if not isinstance(asof, str) or not asof or not _is_iso_datetime(asof):
        _err(errors, "asof must be a non-empty ISO datetime string")

    horizons = doc.get("horizons_trading_days")
    if (
        not isinstance(horizons, list)
        or not horizons
        or not all(isinstance(x, int) and x >= 0 for x in horizons)
    ):
        _err(errors, "horizons_trading_days must be a non-empty list[int>=0]")

    scores = doc.get("scores")
    if not isinstance(scores, dict) or not scores:
        _err(
            errors,
            "scores must be a non-empty object mapping symbol -> horizon -> payload",
        )
        return errors

    for sym, by_h in scores.items():
        if not isinstance(sym, str) or not sym:
            _err(errors, "scores keys must be non-empty symbol strings")
            continue
        if not isinstance(by_h, dict) or not by_h:
            _err(errors, f"scores[{sym}] must be an object keyed by horizon")
            continue

        for hk, payload in by_h.items():
            h = _as_int_key(hk)
            if h is None:
                _err(
                    errors,
                    f"scores[{sym}] horizon key must be int or digit-string, got {hk!r}",
                )
                continue
            if horizons and h not in horizons:
                _err(errors, f"scores[{sym}][{h}] horizon not in horizons_trading_days")
            if not isinstance(payload, dict):
                _err(errors, f"scores[{sym}][{h}] must be an object")
                continue

            fs = payload.get("forecast_score")
            if not isinstance(fs, (int, float)) or fs < 0 or fs > 1:
                _err(errors, f"scores[{sym}][{h}].forecast_score must be in [0,1]")

            pts = payload.get("points")
            mx = payload.get("max_points")
            if not isinstance(pts, int) or pts < 0:
                _err(errors, f"scores[{sym}][{h}].points must be int >=0")
            if not isinstance(mx, int) or mx <= 0:
                _err(errors, f"scores[{sym}][{h}].max_points must be int >0")

            cats = payload.get("categories")
            if not isinstance(cats, dict):
                _err(errors, f"scores[{sym}][{h}].categories must be an object")
                continue

            for code in ["A", "B", "C", "D", "E"]:
                if code not in cats:
                    _err(errors, f"scores[{sym}][{h}].categories missing {code}")
                    continue
                cat = cats.get(code)
                if not isinstance(cat, dict):
                    _err(
                        errors,
                        f"scores[{sym}][{h}].categories[{code}] must be an object",
                    )
                    continue

                checks = cat.get("checks")
                if not isinstance(checks, list) or len(checks) != 6:
                    _err(
                        errors,
                        f"scores[{sym}][{h}].categories[{code}].checks must be list length 6",
                    )
                    continue

                for i, chk in enumerate(checks):
                    if not isinstance(chk, dict):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}] must be object",
                        )
                        continue
                    if not isinstance(chk.get("label"), str) or not chk.get("label"):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].label must be non-empty string",
                        )
                    if not isinstance(chk.get("meaning"), str) or not chk.get(
                        "meaning"
                    ):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].meaning must be non-empty string",
                        )
                    sc = chk.get("score")
                    if sc not in (0, 1, 2):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].score must be 0/1/2",
                        )
                    if "metrics" in chk and not isinstance(chk.get("metrics"), dict):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].metrics must be object",
                        )

                    sq = chk.get("source_quality")
                    if sq not in ("real", "proxy", "neutral", "disabled"):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].source_quality must be one of real/proxy/neutral/disabled",
                        )

                    fb = chk.get("fallback_used")
                    if not isinstance(fb, bool):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].fallback_used must be bool",
                        )

                    if not isinstance(chk.get("raw_inputs"), dict):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].raw_inputs must be object",
                        )

                    if "u" not in chk:
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].u must be present",
                        )
                    elif chk.get("u") is not None and not isinstance(
                        chk.get("u"), (int, float)
                    ):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].u must be number or null",
                        )

                    if not isinstance(chk.get("cutoffs"), dict):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].cutoffs must be object",
                        )

                    if not isinstance(chk.get("orientation"), str) or not chk.get(
                        "orientation"
                    ):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].orientation must be non-empty string",
                        )

                    if "margin_to_flip" not in chk:
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].margin_to_flip must be present",
                        )
                    elif chk.get("margin_to_flip") is not None and not isinstance(
                        chk.get("margin_to_flip"), (int, float)
                    ):
                        _err(
                            errors,
                            f"scores[{sym}][{h}].categories[{code}].checks[{i}].margin_to_flip must be number or null",
                        )

            diag = payload.get("diagnostics")
            if diag is not None and not isinstance(diag, dict):
                _err(
                    errors,
                    f"scores[{sym}][{h}].diagnostics must be an object when present",
                )

    return errors


def _horizon_payload(
    scores: Dict[str, Any], symbol: str, horizon: int
) -> Dict[str, Any]:
    by_symbol = scores.get(symbol)
    if not isinstance(by_symbol, dict):
        raise SystemExit(f"ERR: symbol not found: {symbol}")

    payload = by_symbol.get(horizon)
    if payload is None:
        payload = by_symbol.get(str(horizon))
    if not isinstance(payload, dict):
        raise SystemExit(f"ERR: horizon not found for {symbol}: {horizon}")

    return payload


def print_audit(doc: Dict[str, Any], *, symbol: str, horizons: List[int]) -> None:
    scores = doc.get("scores")
    if not isinstance(scores, dict):
        raise SystemExit("ERR: scores must be an object before audit can print")

    for horizon in horizons:
        payload = _horizon_payload(scores, symbol, horizon)
        cats = payload.get("categories")
        if not isinstance(cats, dict):
            raise SystemExit(f"ERR: categories missing for {symbol} H{horizon}")

        print(f"forecast-audit symbol={symbol} horizon={horizon}")
        for code in ["A", "B", "C", "D", "E"]:
            cat = cats.get(code)
            if not isinstance(cat, dict):
                continue
            checks = cat.get("checks")
            if not isinstance(checks, list):
                continue
            for idx, chk in enumerate(checks, start=1):
                if not isinstance(chk, dict):
                    continue
                print(
                    " "
                    f"{code}{idx} "
                    f"label={chk.get('label')} "
                    f"score={chk.get('score')} "
                    f"source_quality={chk.get('source_quality')} "
                    f"fallback_used={chk.get('fallback_used')} "
                    f"u={chk.get('u')} "
                    f"orientation={chk.get('orientation')} "
                    f"margin_to_flip={chk.get('margin_to_flip')} "
                    f"cutoffs={json.dumps(chk.get('cutoffs', {}), sort_keys=True)} "
                    f"raw_inputs={json.dumps(chk.get('raw_inputs', {}), sort_keys=True)}"
                )


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate forecast_scores.v1.json")
    ap.add_argument("--path", required=True, help="Path to forecast_scores.v1.json")
    ap.add_argument(
        "--audit-symbol",
        default="",
        help="Print per-check pre-quant audit fields for this symbol",
    )
    ap.add_argument(
        "--audit-horizons",
        default="",
        help="Comma-separated horizon pair/list for --audit-symbol, e.g. 1,5",
    )
    ap.add_argument(
        "--input-inventory",
        action="store_true",
        help="Print upstream forecast input inventory",
    )
    args = ap.parse_args()

    p = Path(args.path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        print("ERR: top-level must be a JSON object")
        return 1

    errors = validate(doc)
    if errors:
        print("ERR: forecast_scores.v1 validation failed:")
        for e in errors:
            print(" -", e)
        return 1

    print("OK: forecast_scores.v1 valid")

    if args.audit_symbol:
        horizons = [
            int(x.strip())
            for x in str(args.audit_horizons or "").split(",")
            if x.strip()
        ]
        if not horizons:
            horizons = [1, 5]
        print_audit(doc, symbol=args.audit_symbol, horizons=horizons)

    if args.input_inventory:
        print("forecast-input-inventory")
        for row in forecast_input_inventory():
            print(
                f" {row['check']} "
                f"label={row['label']} "
                f"dependency={row['dependency']} "
                f"current_handling={row['current_handling']} "
                f"source_quality_when_missing={row['source_quality_when_missing']} "
                f"missing_behavior={row['missing_behavior']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
