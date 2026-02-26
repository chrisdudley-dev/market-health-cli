#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re as _re
from pathlib import Path
from typing import Any, Dict, List, Union


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
    if not isinstance(horizons, list) or not horizons or not all(isinstance(x, int) and x >= 0 for x in horizons):
        _err(errors, "horizons_trading_days must be a non-empty list[int>=0]")

    scores = doc.get("scores")
    if not isinstance(scores, dict) or not scores:
        _err(errors, "scores must be a non-empty object mapping symbol -> horizon -> payload")
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
                _err(errors, f"scores[{sym}] horizon key must be int or digit-string, got {hk!r}")
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
                    _err(errors, f"scores[{sym}][{h}].categories[{code}] must be an object")
                    continue

                checks = cat.get("checks")
                if not isinstance(checks, list) or len(checks) != 6:
                    _err(errors, f"scores[{sym}][{h}].categories[{code}].checks must be list length 6")
                    continue

                for i, chk in enumerate(checks):
                    if not isinstance(chk, dict):
                        _err(errors, f"scores[{sym}][{h}].categories[{code}].checks[{i}] must be object")
                        continue
                    if not isinstance(chk.get("label"), str) or not chk.get("label"):
                        _err(errors, f"scores[{sym}][{h}].categories[{code}].checks[{i}].label must be non-empty string")
                    if not isinstance(chk.get("meaning"), str) or not chk.get("meaning"):
                        _err(errors, f"scores[{sym}][{h}].categories[{code}].checks[{i}].meaning must be non-empty string")
                    sc = chk.get("score")
                    if sc not in (0, 1, 2):
                        _err(errors, f"scores[{sym}][{h}].categories[{code}].checks[{i}].score must be 0/1/2")
                    if "metrics" in chk and not isinstance(chk.get("metrics"), dict):
                        _err(errors, f"scores[{sym}][{h}].categories[{code}].checks[{i}].metrics must be object")

            diag = payload.get("diagnostics")
            if diag is not None and not isinstance(diag, dict):
                _err(errors, f"scores[{sym}][{h}].diagnostics must be an object when present")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate forecast_scores.v1.json")
    ap.add_argument("--path", required=True, help="Path to forecast_scores.v1.json")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
