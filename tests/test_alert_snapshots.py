import json
import sqlite3
from pathlib import Path

from market_health.alert_snapshots import (
    collect_held_position_snapshots,
    collect_held_position_snapshots_from_file,
    write_held_position_snapshots,
    write_held_position_snapshots_from_file,
)
from market_health.alert_store import count_rows, start_run


def _ui_doc() -> dict:
    return {
        "schema": "jerboa.market_health.ui.v1",
        "asof": "2026-04-30T15:00:00Z",
        "data": {
            "positions": {
                "schema": "positions.v1",
                "positions": [
                    {"symbol": "spy", "qty": 2, "last_price": "$510.25"},
                    {
                        "Symbol": "XLF",
                        "State": "DMG",
                        "Stop": "43.10",
                        "Buy": "45.25",
                    },
                ],
            },
            "sectors": [
                {
                    "symbol": "SPY",
                    "C": "72.5",
                    "Blend": "70.0",
                    "H1": "66.0",
                    "H5": "61.0",
                    "State": "clean",
                    "SupATR": "1.2",
                    "ResATR": "0.8",
                },
                {
                    "Sym": "XLF",
                    "C": 55,
                    "Blend": 58,
                    "H1": 49,
                    "H5": 47,
                    "SupATR": 1.9,
                    "ResATR": 1.1,
                    "Last": 44.5,
                },
            ],
        },
    }


def test_collect_held_position_snapshots_merges_position_and_sector_fields() -> None:
    snapshots = collect_held_position_snapshots(_ui_doc())

    assert [s.symbol for s in snapshots] == ["SPY", "XLF"]

    spy = snapshots[0]
    assert spy.ts_utc == "2026-04-30T15:00:00Z"
    assert spy.current_score == 72.5
    assert spy.blend_score == 70.0
    assert spy.h1_score == 66.0
    assert spy.h5_score == 61.0
    assert spy.state == "clean"
    assert spy.stop_price is None
    assert spy.buy_price is None
    assert spy.sup_atr == 1.2
    assert spy.res_atr == 0.8
    assert spy.last_price == 510.25
    assert spy.source is not None
    assert spy.source["position"]["symbol"] == "spy"
    assert spy.source["sector"]["symbol"] == "SPY"

    xlf = snapshots[1]
    assert xlf.current_score == 55.0
    assert xlf.state == "DMG"
    assert xlf.stop_price == 43.10
    assert xlf.buy_price == 45.25
    assert xlf.last_price == 44.5


def test_collect_handles_empty_positions() -> None:
    doc = {
        "schema": "jerboa.market_health.ui.v1",
        "asof": "2026-04-30T15:00:00Z",
        "data": {"positions": {"positions": []}, "sectors": []},
    }

    assert collect_held_position_snapshots(doc) == []


def test_collect_from_file(tmp_path: Path) -> None:
    ui_path = tmp_path / "market_health.ui.v1.json"
    ui_path.write_text(json.dumps(_ui_doc()), encoding="utf-8")

    snapshots = collect_held_position_snapshots_from_file(ui_path)

    assert [s.symbol for s in snapshots] == ["SPY", "XLF"]


def test_write_held_position_snapshots_to_alert_store(tmp_path: Path) -> None:
    db = tmp_path / "market_health_alerts.v1.sqlite"
    run_id = start_run(db_path=db, mode="dry-run", trigger_name="manual")

    row_ids = write_held_position_snapshots(
        db_path=db,
        run_id=run_id,
        ui_doc=_ui_doc(),
    )

    assert row_ids == [1, 2]
    assert count_rows(db, "symbol_snapshots") == 2

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        """
        SELECT symbol, current_score, blend_score, h1_score, h5_score,
               state, stop_price, buy_price, sup_atr, res_atr, last_price,
               source_json
        FROM symbol_snapshots
        ORDER BY id
        """
    ).fetchall()
    conn.close()

    assert rows[0][0] == "SPY"
    assert rows[0][1:11] == (
        72.5,
        70.0,
        66.0,
        61.0,
        "clean",
        None,
        None,
        1.2,
        0.8,
        510.25,
    )
    assert json.loads(rows[0][11])["schema"] == "jerboa.market_health.ui.v1"

    assert rows[1][0] == "XLF"
    assert rows[1][1:11] == (
        55.0,
        58.0,
        49.0,
        47.0,
        "DMG",
        43.10,
        45.25,
        1.9,
        1.1,
        44.5,
    )


def test_write_from_file(tmp_path: Path) -> None:
    db = tmp_path / "market_health_alerts.v1.sqlite"
    ui_path = tmp_path / "market_health.ui.v1.json"
    ui_path.write_text(json.dumps(_ui_doc()), encoding="utf-8")
    run_id = start_run(db_path=db, mode="dry-run", trigger_name="manual")

    row_ids = write_held_position_snapshots_from_file(
        db_path=db,
        run_id=run_id,
        ui_path=ui_path,
    )

    assert row_ids == [1, 2]
    assert count_rows(db, "symbol_snapshots") == 2


def _score_payload(symbol: str, total: int) -> dict:
    scores = []
    remaining = int(total)
    for _ in range(30):
        value = min(2, max(0, remaining))
        scores.append(value)
        remaining -= value

    idx = 0
    categories = {}
    for cat in ("A", "B", "C", "D", "E"):
        checks = []
        for i in range(6):
            checks.append({"id": f"{cat}{i + 1}", "score": scores[idx]})
            idx += 1
        categories[cat] = {"checks": checks}

    return {"symbol": symbol, "categories": categories}


def test_collect_derives_scores_from_nested_ui_contract_payloads() -> None:
    h1 = _score_payload("SPY", 37)
    h1["forecast_score"] = 37 / 60
    h1["structure_summary"] = {
        "state_tags": ["near_damage_zone", "overhead_heavy", "breakout_ready"],
        "support_cushion_atr": 0.25,
        "overhead_resistance_atr": 0.75,
        "tactical_stop_candidate": 99.5,
        "stop_buy_candidate": 101.25,
    }

    h5 = _score_payload("SPY", 33)
    h5["forecast_score"] = 33 / 60

    doc = {
        "schema": "market_health.ui.v1",
        "asof": "2026-05-04T16:52:34Z",
        "data": {
            "positions": {
                "positions": [
                    {
                        "symbol": "SPY",
                        "qty": 1,
                        "mark_price": "100.25",
                    }
                ]
            },
            "sectors": [_score_payload("SPY", 34)],
            "forecast_scores": {
                "horizons_trading_days": [1, 5],
                "scores": {"SPY": {"1": h1, "5": h5}},
            },
        },
    }

    snapshots = collect_held_position_snapshots(doc)

    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.symbol == "SPY"
    assert round(snap.current_score or 0, 2) == 56.67
    assert round(snap.h1_score or 0, 2) == 68.33
    assert round(snap.h5_score or 0, 2) == 61.67
    assert round(snap.blend_score or 0, 2) == 60.83
    assert snap.state == "DMG,OH,BRK"
    assert snap.sup_atr == 0.25
    assert snap.res_atr == 0.75
    assert snap.stop_price == 99.5
    assert snap.buy_price == 101.25
    assert snap.last_price == 100.25
