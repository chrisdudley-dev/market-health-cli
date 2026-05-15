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


_SCORE_CAT_KEYS = ("A", "B", "C", "D", "E")


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _looks_like_score_payload(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False

    categories = value.get("categories")
    if isinstance(categories, Mapping):
        return all(key in categories for key in _SCORE_CAT_KEYS)

    return all(key in value for key in _SCORE_CAT_KEYS)


def _cat_node(payload: Mapping[str, Any], cat: str) -> Any:
    categories = payload.get("categories")
    if isinstance(categories, Mapping):
        return categories.get(cat)
    return payload.get(cat)


def _checks_for_cat(
    payload: Optional[Mapping[str, Any]], cat: str
) -> List[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []

    node = _cat_node(payload, cat)
    if isinstance(node, Mapping) and isinstance(node.get("checks"), list):
        return [x for x in node["checks"] if isinstance(x, Mapping)]
    if isinstance(node, list):
        return [x for x in node if isinstance(x, Mapping)]
    return []


def _sum_checks(checks: Iterable[Mapping[str, Any]]) -> int:
    total = 0
    for check in list(checks)[:6]:
        score = check.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            total += int(score)
    return total


def _payload_utility(payload: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not isinstance(payload, Mapping):
        return None

    total = 0
    for cat in _SCORE_CAT_KEYS:
        total += _sum_checks(_checks_for_cat(payload, cat))

    return max(0.0, min(1.0, float(total) / 60.0))


def _as_percent(value: Optional[float]) -> Optional[float]:
    return None if value is None else float(value) * 100.0


def _forecast_payload(
    ui_doc: Mapping[str, Any],
    symbol: str,
    horizon: int,
) -> Optional[Mapping[str, Any]]:
    data = ui_doc.get("data")
    if not isinstance(data, Mapping):
        return None

    forecast_doc = data.get("forecast_scores")
    if not isinstance(forecast_doc, Mapping):
        return None

    scores = forecast_doc.get("scores")
    if not isinstance(scores, Mapping):
        return None

    by_symbol = scores.get(symbol)
    if not isinstance(by_symbol, Mapping):
        return None

    payload = by_symbol.get(str(horizon), by_symbol.get(horizon))
    return payload if isinstance(payload, Mapping) else None


def _forecast_score(payload: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not isinstance(payload, Mapping):
        return None

    for key in ("forecast_score", "score", "utility", "blend", "blended", "current"):
        score = _as_float(payload.get(key))
        if score is None:
            continue

        if abs(score) > 1.000001:
            score = score / 100.0
        return max(0.0, min(1.0, score))

    return None


def _forecast_utility(
    payload: Optional[Mapping[str, Any]],
    current_utility: Optional[float],
) -> Optional[float]:
    score = _first_not_none(_forecast_score(payload), _payload_utility(payload))
    if score is None:
        return None

    return max(0.0, min(1.0, float(score)))


def _blend_utility(
    current_utility: Optional[float],
    h1_utility: Optional[float],
    h5_utility: Optional[float],
) -> Optional[float]:
    pieces = []
    for weight, value in (
        (0.50, current_utility),
        (0.25, h1_utility),
        (0.25, h5_utility),
    ):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            pieces.append((weight, max(0.0, min(1.0, float(value)))))

    if not pieces:
        return None

    return sum(weight * value for weight, value in pieces) / sum(
        weight for weight, _value in pieces
    )


def _structure_summary(payload: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        return {}

    summary = payload.get("structure_summary")
    return summary if isinstance(summary, Mapping) else {}


def _compact_state_text_from_structure(structure: Mapping[str, Any]) -> Optional[str]:
    tags = structure.get("state_tags")
    if isinstance(tags, list):
        mapping = {
            "near_damage_zone": "DMG",
            "damage_zone": "DMG",
            "overhead_heavy": "OH",
            "breakout_ready": "BRK",
            "reclaim_ready": "RCL",
        }
        out: List[str] = []
        for tag in tags:
            text = str(tag).strip()
            if not text:
                continue
            compact = mapping.get(text, text.upper())
            if compact not in out:
                out.append(compact)
        if out:
            return ",".join(out)

    return _as_text(
        _first_not_none(
            structure.get("state_text"),
            structure.get("state"),
        )
    )


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

        current_payload = sector if _looks_like_score_payload(sector) else None
        current_utility = _payload_utility(current_payload)

        h1_payload = _forecast_payload(ui_doc, symbol, 1)
        h5_payload = _forecast_payload(ui_doc, symbol, 5)
        h1_utility = _forecast_utility(h1_payload, current_utility)
        h5_utility = _forecast_utility(h5_payload, current_utility)
        blend_utility = _blend_utility(current_utility, h1_utility, h5_utility)

        h1_structure = _structure_summary(h1_payload)
        h5_structure = _structure_summary(h5_payload)
        structure = h1_structure or h5_structure

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
                current_score=_first_not_none(
                    _as_float(pick("current_score", "current", "C", "score")),
                    _as_percent(current_utility),
                ),
                blend_score=_first_not_none(
                    _as_float(pick("blend_score", "Blend", "blend")),
                    _as_percent(blend_utility),
                ),
                h1_score=_first_not_none(
                    _as_float(pick("h1_score", "H1", "h1")),
                    _as_percent(h1_utility),
                ),
                h5_score=_first_not_none(
                    _as_float(pick("h5_score", "H5", "h5")),
                    _as_percent(h5_utility),
                ),
                state=_first_not_none(
                    _as_text(pick("state", "State")),
                    _compact_state_text_from_structure(structure),
                ),
                stop_price=_first_not_none(
                    _as_float(pick("stop_price", "Stop", "stop")),
                    _as_float(structure.get("tactical_stop_candidate")),
                ),
                buy_price=_first_not_none(
                    _as_float(pick("buy_price", "Buy", "buy")),
                    _as_float(structure.get("stop_buy_candidate")),
                ),
                sup_atr=_first_not_none(
                    _as_float(pick("sup_atr", "SupATR", "support_atr")),
                    _as_float(structure.get("support_cushion_atr")),
                    _as_float(structure.get("support_atr")),
                    _as_float(structure.get("sup_atr")),
                ),
                res_atr=_first_not_none(
                    _as_float(pick("res_atr", "ResATR", "resistance_atr")),
                    _as_float(structure.get("overhead_resistance_atr")),
                    _as_float(structure.get("resistance_atr")),
                    _as_float(structure.get("res_atr")),
                ),
                last_price=_as_float(
                    pick("last_price", "Last", "price", "mark", "mark_price")
                ),
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
