from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from market_health.alert_store import add_symbol_snapshot


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _as_list(value: Any) -> List[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, Mapping)]


def _first_value(row: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text or text in {"-", "—", "N/A", "n/a", "None", "null"}:
        return None

    text = text.replace("%", "").replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _symbol_from_row(row: Mapping[str, Any]) -> Optional[str]:
    value = _first_value(row, ("symbol", "Symbol", "sym", "Sym", "ticker", "Ticker"))
    text = _as_text(value)
    return text.upper() if text else None


def _rows_by_symbol(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        symbol = _symbol_from_row(row)
        if symbol:
            out[symbol] = row
    return out


def _position_rows(ui_doc: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    data = ui_doc.get("data")
    if not isinstance(data, Mapping):
        return []

    positions_doc = data.get("positions")
    if isinstance(positions_doc, Mapping):
        return _as_list(positions_doc.get("positions"))
    return _as_list(positions_doc)


def _sector_rows(ui_doc: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    data = ui_doc.get("data")
    if not isinstance(data, Mapping):
        return []
    return _as_list(data.get("sectors"))


@dataclass(frozen=True)
class HeldPositionSnapshot:
    symbol: str
    ts_utc: str
    current_score: Optional[float] = None
    blend_score: Optional[float] = None
    h1_score: Optional[float] = None
    h5_score: Optional[float] = None
    state: Optional[str] = None
    stop_price: Optional[float] = None
    buy_price: Optional[float] = None
    sup_atr: Optional[float] = None
    res_atr: Optional[float] = None
    last_price: Optional[float] = None
    source: Optional[Dict[str, Any]] = None


def collect_held_position_snapshots(
    ui_doc: Mapping[str, Any],
    *,
    ts_utc: Optional[str] = None,
) -> List[HeldPositionSnapshot]:
    """Normalize held-position rows from a market_health.ui.v1-style document.

    This collector intentionally consumes JSON/artifact data rather than terminal
    dashboard output. It accepts multiple field spellings so later UI contract
    changes can be adapted without breaking the storage layer.
    """

    snapshot_ts = ts_utc or _as_text(ui_doc.get("asof")) or _utc_now_iso()
    sectors_by_symbol = _rows_by_symbol(_sector_rows(ui_doc))

    snapshots: List[HeldPositionSnapshot] = []
    for pos in _position_rows(ui_doc):
        symbol = _symbol_from_row(pos)
        if not symbol:
            continue

        sector = sectors_by_symbol.get(symbol, {})

        def pick(*names: str) -> Any:
            return (
                _first_value(pos, names)
                if _first_value(pos, names) is not None
                else _first_value(sector, names)
            )

        source = {
            "schema": ui_doc.get("schema"),
            "asof": ui_doc.get("asof"),
            "position": dict(pos),
        }
        if sector:
            source["sector"] = dict(sector)

        snapshots.append(
            HeldPositionSnapshot(
                symbol=symbol,
                ts_utc=snapshot_ts,
                current_score=_as_float(pick("current_score", "current", "C", "score")),
                blend_score=_as_float(pick("blend_score", "Blend", "blend")),
                h1_score=_as_float(pick("h1_score", "H1", "h1")),
                h5_score=_as_float(pick("h5_score", "H5", "h5")),
                state=_as_text(pick("state", "State")),
                stop_price=_as_float(pick("stop_price", "Stop", "stop")),
                buy_price=_as_float(pick("buy_price", "Buy", "buy")),
                sup_atr=_as_float(pick("sup_atr", "SupATR", "support_atr")),
                res_atr=_as_float(pick("res_atr", "ResATR", "resistance_atr")),
                last_price=_as_float(pick("last_price", "Last", "price", "mark")),
                source=source,
            )
        )

    return snapshots


def load_ui_doc(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"expected object JSON document: {path}")
    return data


def collect_held_position_snapshots_from_file(path: Path) -> List[HeldPositionSnapshot]:
    return collect_held_position_snapshots(load_ui_doc(path))


def write_held_position_snapshots(
    *,
    db_path: Path,
    run_id: int,
    ui_doc: Mapping[str, Any],
    ts_utc: Optional[str] = None,
) -> List[int]:
    row_ids: List[int] = []
    for snap in collect_held_position_snapshots(ui_doc, ts_utc=ts_utc):
        row_ids.append(
            add_symbol_snapshot(
                db_path=db_path,
                run_id=run_id,
                symbol=snap.symbol,
                ts_utc=snap.ts_utc,
                is_held=True,
                current_score=snap.current_score,
                blend_score=snap.blend_score,
                h1_score=snap.h1_score,
                h5_score=snap.h5_score,
                state=snap.state,
                stop_price=snap.stop_price,
                buy_price=snap.buy_price,
                sup_atr=snap.sup_atr,
                res_atr=snap.res_atr,
                last_price=snap.last_price,
                source=snap.source,
            )
        )
    return row_ids


def write_held_position_snapshots_from_file(
    *,
    db_path: Path,
    run_id: int,
    ui_path: Path,
    ts_utc: Optional[str] = None,
) -> List[int]:
    return write_held_position_snapshots(
        db_path=db_path,
        run_id=run_id,
        ui_doc=load_ui_doc(ui_path),
        ts_utc=ts_utc,
    )
