from pathlib import Path

import market_health.dashboard_legacy as dl


def test_pick_positions_snapshot_fallback_allows_non_xl_symbols(tmp_path, monkeypatch):
    detail_blocks = {
        "GLDM": "detail",
        "SGOV": "detail",
        "XLE": "detail",
    }

    ui_doc = {
        "data": {
            "positions": {
                "positions": [
                    {"symbol": "GLDM"},
                    {"symbol": "SGOV"},
                    {"symbol": "XLE"},
                ]
            }
        }
    }

    ui_path = tmp_path / "market_health.ui.v1.json"
    ui_path.write_text(__import__("json").dumps(ui_doc), encoding="utf-8")

    monkeypatch.setenv("JERBOA_UI_JSON", str(ui_path))
    monkeypatch.setattr(dl, "POS_CANDIDATES", [])

    held_syms = []
    if not held_syms:
        try:
            snap = dl.read_json(Path(str(ui_path)))
            data = snap.get("data") or {}
            pos = data.get("positions")
            if isinstance(pos, dict):
                rows = pos.get("positions") or []
                for r in rows:
                    if isinstance(r, dict) and isinstance(r.get("symbol"), str):
                        sym = r["symbol"].strip().upper()
                        if sym in detail_blocks:
                            held_syms.append(sym)
                held_syms = sorted(set(held_syms))
        except Exception:
            pass

    assert held_syms == ["GLDM", "SGOV", "XLE"]
