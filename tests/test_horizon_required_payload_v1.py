import hashlib
import json
from pathlib import Path

def _find_symbol_map(x):
    # Heuristic: find dict[symbol] -> dict[horizon] -> payload
    if isinstance(x, dict):
        if x and all(isinstance(k, str) for k in x.keys()):
            for v in x.values():
                if isinstance(v, dict) and ((1 in v and 5 in v) or ("1" in v and "5" in v)):
                    return x
        for v in x.values():
            r = _find_symbol_map(v)
            if r is not None:
                return r
    return None

def _h(obj) -> str:
    b = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b).hexdigest()

def test_all_checks_use_horizon_and_hash_diff():
    doc = json.loads(Path("tests/fixtures/golden.forecast_scores.v1.json").read_text(encoding="utf-8"))
    sym_map = _find_symbol_map(doc)
    assert sym_map is not None, "Could not locate symbol->horizon map in golden fixture"

    dims = ["A", "B", "C", "D", "E"]

    for sym, by_h in sym_map.items():
        h1 = by_h.get(1) or by_h.get("1")
        h5 = by_h.get(5) or by_h.get("5")
        assert isinstance(h1, dict) and isinstance(h5, dict)

        cats1 = h1.get("categories") or {}
        cats5 = h5.get("categories") or {}

        for dim in dims:
            c1 = cats1.get(dim) or {}
            c5 = cats5.get(dim) or {}

            checks1 = c1.get("checks") or []
            checks5 = c5.get("checks") or []
            assert len(checks1) >= 6 and len(checks5) >= 6

            for i in range(6):
                a = checks1[i]
                b = checks5[i]
                assert isinstance(a, dict) and isinstance(b, dict)

                assert a.get("horizon_days") == 1, f"{sym} {dim}{i+1}: missing/incorrect horizon_days for H1"
                assert b.get("horizon_days") == 5, f"{sym} {dim}{i+1}: missing/incorrect horizon_days for H5"

                ma = a.get("metrics"); mb = b.get("metrics")
                assert isinstance(ma, dict) and isinstance(mb, dict)
                assert ma.get("horizon_days") == 1
                assert mb.get("horizon_days") == 5
                assert "horizon_scale" in ma and "horizon_scale" in mb

                assert _h(a) != _h(b), f"{sym} {dim}{i+1}: check hash unexpectedly identical across horizons"
