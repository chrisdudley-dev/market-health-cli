#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from types import SimpleNamespace
from market_health.engine import compute_scores
from market_health.recommendations_engine import recommend
from market_health.positions_sectorize import sectorize_positions

from market_health.trading_days import add_trading_days
from market_health.ledger import append_event
import json


def _load_swaps_today() -> tuple[str, int, Path]:
    """Return (today_iso, swaps_today, state_path). Resilient to missing/invalid state."""
    home_root = Path(os.environ.get("JERBOA_HOME_WIN") or os.path.expanduser("~"))
    state_p = (
        home_root
        / ".cache"
        / "jerboa"
        / "state"
        / "recommendations_swaps_today.v1.json"
    )
    state_p.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    swaps_today = 0
    try:
        if state_p.exists():
            st = json.loads(state_p.read_text(encoding="utf-8"))
            if isinstance(st, dict) and st.get("date") == today:
                swaps_today = int(st.get("count", 0) or 0)
    except Exception:
        swaps_today = 0
    return today, swaps_today, state_p


def _bump_swaps_today(*, today: str, swaps_today: int, state_p: Path) -> None:
    try:
        state = {"date": today, "count": swaps_today + 1}
        state_p.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except Exception:
        pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _age_seconds_from_iso(value: Any):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    except Exception:
        return None


def _max_iso_skew_seconds(*values: Any):
    xs = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
            xs.append(int(dt.timestamp()))
        except Exception:
            pass
    if len(xs) < 2:
        return 0 if xs else None
    return max(xs) - min(xs)


def _parse_iso_utc(value: Any):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_market_calendar_module():
    try:
        import pandas_market_calendars as mcal

        return mcal
    except ModuleNotFoundError:
        return None


def _is_market_session_fresh(value: Any, max_age_minutes: int = 15):
    dt = _parse_iso_utc(value)
    if dt is None:
        return False

    now_utc = datetime.now(timezone.utc)
    ttl_seconds = max_age_minutes * 60

    try:
        from zoneinfo import ZoneInfo

        session_tz = ZoneInfo("America/New_York")
    except Exception:
        session_tz = timezone(timedelta(hours=-5), "ET")

    mcal = _get_market_calendar_module()

    if mcal is None:
        now_et = now_utc.astimezone(session_tz)
        dt_et = dt.astimezone(session_tz)

        open_mins = 9 * 60 + 30
        close_mins = 16 * 60
        now_mins = now_et.hour * 60 + now_et.minute

        in_live_session = (
            now_et.weekday() < 5
            and open_mins <= now_mins <= close_mins
        )

        if in_live_session:
            return (
                dt_et.date() == now_et.date()
                and 0 <= (now_utc - dt).total_seconds() <= ttl_seconds
            )

        return _is_same_or_last_completed_session(value)

    sched = mcal.get_calendar("NYSE").schedule(
        start_date=(now_utc - timedelta(days=10)).date().isoformat(),
        end_date=(now_utc + timedelta(days=2)).date().isoformat(),
    )
    if sched.empty:
        return False

    rows = []
    for _, row in sched.iterrows():
        open_ts = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        close_ts = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        rows.append((open_ts, close_ts))

    for open_ts, close_ts in rows:
        if open_ts <= now_utc <= close_ts:
            return (
                open_ts <= dt <= close_ts
                and 0 <= (now_utc - dt).total_seconds() <= ttl_seconds
            )

    return _is_same_or_last_completed_session(value)


def _is_same_or_last_completed_session(value: Any):
    dt = _parse_iso_utc(value)
    if dt is None:
        return False

    now_utc = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        session_tz = ZoneInfo("America/New_York")
    except Exception:
        session_tz = timezone(timedelta(hours=-5), "ET")

    dt_session = dt.astimezone(session_tz).date().isoformat()
    mcal = _get_market_calendar_module()

    if mcal is None:
        try:
            from zoneinfo import ZoneInfo

            et_tz = ZoneInfo("America/New_York")
        except Exception:
            et_tz = timezone(timedelta(hours=-5), "ET")

        now_et = now_utc.astimezone(et_tz)
        dt_et = dt.astimezone(et_tz)

        def _last_weekday(d):
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        mins_now = now_et.hour * 60 + now_et.minute
        open_mins = 9 * 60 + 30

        ref_date = now_et.date()
        if now_et.weekday() < 5 and mins_now < open_mins:
            ref_date -= timedelta(days=1)
        ref_date = _last_weekday(ref_date)
        return dt_et.date() == ref_date

    sched = mcal.get_calendar("NYSE").schedule(
        start_date=(now_utc - timedelta(days=10)).date().isoformat(),
        end_date=(now_utc + timedelta(days=2)).date().isoformat(),
    )
    if sched.empty:
        return False

    rows = []
    for idx, row in sched.iterrows():
        open_ts = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        close_ts = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        session_label = str(idx.date() if hasattr(idx, "date") else idx)
        rows.append((session_label, open_ts, close_ts))

    # If market is currently live, accept the current session.
    for session_label, open_ts, close_ts in rows:
        if open_ts <= now_utc <= close_ts:
            return dt_session == session_label

    # Otherwise accept the most recent completed scheduled session.
    prior_rows = [r for r in rows if r[2] <= now_utc]
    if not prior_rows:
        return False

    last_completed_session = prior_rows[-1][0]
    return dt_session == last_completed_session


def _mtime_epoch(p: Path) -> int:
    try:
        return int(p.stat().st_mtime)
    except Exception:
        return 0


def _iso_from_epoch(epoch: int) -> str | None:
    if epoch <= 0:
        return None
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _is_file_fresh(p: Path, *, max_age_minutes: int) -> bool:
    if max_age_minutes <= 0:
        return True
    ts = _mtime_epoch(p)
    if ts <= 0:
        return False
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return (now_ts - ts) <= (max_age_minutes * 60)


def _first_number(d: Dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.replace(",", ""))
            except Exception:
                pass
    return None


def _first_str(d: Dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _position_symbol(row: Dict[str, Any]) -> str | None:
    sym = _first_str(row, "symbol", "ticker", "underlying")
    return sym.upper() if sym else None


def _position_market_value(row: Dict[str, Any]) -> float:
    mv = _first_number(
        row,
        "market_value",
        "marketValue",
        "position_market_value",
        "value",
        "notional",
        "notional_value",
    )
    if mv is not None:
        return float(mv)

    qty = _first_number(
        row,
        "quantity",
        "qty",
        "longQuantity",
        "shortQuantity",
    )
    px = _first_number(
        row,
        "mark",
        "mark_price",
        "marketPrice",
        "price",
        "last_price",
    )
    if qty is not None and px is not None:
        return float(qty) * float(px)

    return 0.0


def aggregate_positions_for_recommendation(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    account_sets: Dict[str, set[str]] = {}
    order: List[str] = []

    if not isinstance(rows, list):
        return []

    for row in rows:
        if not isinstance(row, dict):
            continue

        sym = _first_str(row, "symbol", "ticker", "underlying")
        if not sym:
            continue
        sym = sym.upper()

        qty = (
            _first_number(
                row,
                "quantity",
                "qty",
                "shares",
                "longQuantity",
                "settledLongQuantity",
            )
            or 0.0
        )

        mv = (
            _first_number(
                row,
                "market_value",
                "marketValue",
                "value",
                "market_value_usd",
            )
            or 0.0
        )

        wt = _first_number(
            row,
            "weight",
            "portfolio_weight",
            "portfolioWeight",
        )

        acct = _first_str(
            row,
            "account_id",
            "account",
            "account_number",
            "accountNumber",
            "account_hash",
            "accountHash",
        )

        if sym not in buckets:
            buckets[sym] = {
                "symbol": sym,
                "quantity": 0.0,
                "market_value": 0.0,
                "weight": 0.0,
                "rows": 0,
            }
            account_sets[sym] = set()
            order.append(sym)

        buckets[sym]["quantity"] += qty
        buckets[sym]["market_value"] += mv
        buckets[sym]["rows"] += 1

        if wt is not None:
            buckets[sym]["weight"] += wt

        if acct:
            account_sets[sym].add(acct)

    total_mv = sum(float(buckets[s]["market_value"]) for s in order)
    out: List[Dict[str, Any]] = []

    for sym in order:
        item = dict(buckets[sym])
        item["accounts"] = sorted(account_sets.get(sym, set()))
        item["account_count"] = len(item["accounts"])

        if not item["weight"] and total_mv > 0:
            item["weight"] = float(item["market_value"]) / total_mv

        out.append(item)

    return out


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path):
    try:
        import hashlib

        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:
        return None


def build_computation_fingerprint(
    *,
    snapshot_asof,
    positions_sha256,
    forecast_sha256,
    sectors_sha256,
    positions_asof,
    forecast_asof,
    forecast_source_asof,
    period,
    interval,
    horizon_days,
    forecast_enabled,
    positions_mode,
    raw_positions_count,
    aggregated_positions_count,
):
    import hashlib

    payload = {
        "snapshot_asof": snapshot_asof,
        "positions_sha256": positions_sha256,
        "forecast_sha256": forecast_sha256,
        "sectors_sha256": sectors_sha256,
        "positions_asof": positions_asof,
        "forecast_asof": forecast_asof,
        "forecast_source_asof": forecast_source_asof,
        "period": period,
        "interval": interval,
        "horizon_days": horizon_days,
        "forecast_enabled": bool(forecast_enabled),
        "positions_mode": positions_mode,
        "raw_positions_count": raw_positions_count,
        "aggregated_positions_count": aggregated_positions_count,
    }
    blob = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> bool:
    """Write JSON only if content changed. Returns True if changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new_text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if old_text == new_text:
            return False

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)
    return True


def to_contract(rec_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure top-level recommendations.v1 envelope is correct."""
    if rec_doc.get("schema") != "recommendations.v1":
        raise ValueError("schema must be recommendations.v1")
    return rec_doc


def _intraday_fresh_or_last_completed_session(value, max_age_minutes=15):
    from datetime import datetime, timezone, timedelta, time

    dt = _parse_iso_utc(value)
    if dt is None:
        return False

    now_utc = datetime.now(timezone.utc)
    ttl = timedelta(minutes=max_age_minutes)

    try:
        import pandas_market_calendars as mcal
    except ModuleNotFoundError:
        try:
            from zoneinfo import ZoneInfo

            et_tz = ZoneInfo("America/New_York")
        except Exception:
            et_tz = timezone(timedelta(hours=-5), "ET")

        now_et = now_utc.astimezone(et_tz)
        dt_et = dt.astimezone(et_tz)

        def _last_weekday(d):
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        def _next_weekday(d):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        mins_now = now_et.hour * 60 + now_et.minute
        open_mins = 9 * 60 + 30
        close_mins = 16 * 60

        if now_et.weekday() < 5 and open_mins <= mins_now <= close_mins:
            return dt_et.date() == now_et.date() and dt >= (now_utc - ttl)

        ref_date = now_et.date()
        if now_et.weekday() < 5 and mins_now < open_mins:
            ref_date -= timedelta(days=1)
        ref_date = _last_weekday(ref_date)

        if now_et.weekday() < 5 and mins_now < open_mins:
            next_open_date = now_et.date()
        else:
            next_open_date = now_et.date() + timedelta(days=1)
        next_open_date = _next_weekday(next_open_date)

        last_close_et = datetime.combine(ref_date, time(16, 0), tzinfo=et_tz)
        next_open_et = datetime.combine(next_open_date, time(9, 30), tzinfo=et_tz)

        return dt_et.date() == ref_date or (last_close_et <= dt_et <= next_open_et)

    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(
        start_date=(now_utc - timedelta(days=10)).date().isoformat(),
        end_date=(now_utc + timedelta(days=5)).date().isoformat(),
    )
    if sched.empty:
        return False

    rows = []
    for idx, row in sched.iterrows():
        open_ts = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        close_ts = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        session_label = str(idx.date() if hasattr(idx, "date") else idx)
        rows.append((session_label, open_ts, close_ts))

    try:
        from zoneinfo import ZoneInfo

        session_tz = ZoneInfo("America/New_York")
    except Exception:
        session_tz = timezone(timedelta(hours=-5), "ET")

    dt_session = dt.astimezone(session_tz).date().isoformat()

    for session_label, open_ts, close_ts in rows:
        if open_ts <= now_utc <= close_ts:
            if dt_session != session_label:
                return False
            return dt >= (now_utc - ttl)

    prior_rows = [r for r in rows if r[2] <= now_utc]
    if not prior_rows:
        return False

    last_completed_session, _last_open, last_close = prior_rows[-1]
    future_rows = [r for r in rows if r[1] > now_utc]
    next_open = future_rows[0][1] if future_rows else (now_utc + timedelta(days=5))

    return dt_session == last_completed_session or (last_close <= dt <= next_open)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export recommendations.v1.json to ~/.cache/jerboa/"
    )
    ap.add_argument(
        "--positions", default=os.path.expanduser("~/.cache/jerboa/positions.v1.json")
    )
    ap.add_argument(
        "--out", default=os.path.expanduser("~/.cache/jerboa/recommendations.v1.json")
    )
    ap.add_argument(
        "--sectors",
        nargs="*",
        default=None,
        help="Optional sector list (defaults to scoring engine defaults)",
    )
    ap.add_argument("--period", default="6mo")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--min-improvement", type=float, default=0.12)
    ap.add_argument("--min-floor", type=float, default=0.55)
    ap.add_argument("--max-swaps-per-day", type=int, default=1)
    ap.add_argument("--sector-cap", type=int, default=None)
    ap.add_argument("--turnover-cap", type=float, default=None)
    ap.add_argument(
        "--forecast",
        action="store_true",
        help="Enable forecast-driven recommendation mode (Issue #113)",
    )
    ap.add_argument(
        "--forecast-path",
        default=os.path.expanduser("~/.cache/jerboa/forecast_scores.v1.json"),
    )
    ap.add_argument("--disagreement-veto-edge", type=float, default=0.0)
    ap.add_argument("--cooldown-trading-days", type=int, default=0)
    ap.add_argument("--max-weight", type=float, default=0.25)
    ap.add_argument("--min-distinct", type=int, default=4)
    ap.add_argument("--hhi-cap", type=float, default=0.20)

    ap.add_argument(
        "--max-positions-age-minutes",
        type=int,
        default=int(os.environ.get("JERBOA_POSITIONS_MAX_AGE_MINUTES", "15")),
        help="Refuse personalized recommendations when positions.v1.json is outside the current session freshness window (0 disables the freshness check).",
    )
    ap.add_argument(
        "--max-forecast-age-minutes",
        type=int,
        default=int(os.environ.get("JERBOA_FORECAST_MAX_AGE_MINUTES", "15")),
        help="Report forecast freshness against the current session freshness window (0 disables the freshness check).",
    )
    ap.add_argument(
        "--max-sectors-age-minutes",
        type=int,
        default=int(os.environ.get("JERBOA_SECTORS_MAX_AGE_MINUTES", "15")),
        help="Report sectors freshness against the current session freshness window (0 disables the freshness check).",
    )
    ap.add_argument("--quiet", action="store_true")

    args = ap.parse_args()

    forecast_enabled = bool(getattr(args, "forecast", False)) or str(
        os.environ.get("JERBOA_FORECAST_MODE", "")
    ).lower() in ("1", "true", "yes")

    pos_p = Path(args.positions)
    out_p = Path(args.out)

    positions = read_json(pos_p) if pos_p.exists() else {"positions": []}
    positions_mtime_epoch = _mtime_epoch(pos_p)
    positions_rows = [
        r for r in (positions.get("positions") or []) if isinstance(r, dict)
    ]
    aggregated_positions = aggregate_positions_for_recommendation(positions_rows)
    raw_positions_count = len(positions_rows)
    aggregated_positions_count = len(aggregated_positions)

    positions_asof = _iso_from_epoch(positions_mtime_epoch)
    positions_is_fresh = _intraday_fresh_or_last_completed_session(
        positions_asof,
        int(getattr(args, "max_positions_age_minutes", 15) or 15),
    )
    positions_mtime_epoch = _mtime_epoch(pos_p)
    positions_asof = _iso_from_epoch(positions_mtime_epoch)
    positions_is_fresh = _is_file_fresh(
        pos_p, max_age_minutes=int(getattr(args, "max_positions_age_minutes", 15) or 0)
    )

    forecast_doc = None
    forecast_status = "disabled"
    forecast_p = Path(
        getattr(
            args,
            "forecast_path",
            os.path.expanduser("~/.cache/jerboa/forecast_scores.v1.json"),
        )
    )
    if forecast_enabled:
        forecast_status = "ok"
        try:
            if forecast_p.exists():
                forecast_doc = json.loads(forecast_p.read_text(encoding="utf-8"))
                if not (
                    isinstance(forecast_doc, dict)
                    and forecast_doc.get("schema") == "forecast_scores.v1"
                ):
                    forecast_status = "unreadable"
                    forecast_doc = None
            else:
                forecast_status = "missing"
        except Exception:
            forecast_status = "unreadable"
            forecast_doc = None

    # Prefer cached sector rows if present (keeps exporter fast/offline-friendly on Jerboa).
    sect_cache = Path(os.path.expanduser("~/.cache/jerboa/market_health.sectors.json"))
    score_rows: List[Dict[str, Any]]
    used_source = "compute_scores"
    if sect_cache.exists():
        try:
            obj = json.loads(sect_cache.read_text(encoding="utf-8"))
            if isinstance(obj, list):
                score_rows = obj
                used_source = "market_health.sectors.json"
            elif isinstance(obj, dict):
                # allow a few common shapes
                for key in ("rows", "sectors", "data"):
                    v = obj.get(key)
                    if isinstance(v, list):
                        score_rows = v
                        used_source = f"market_health.sectors.json:{key}"
                        break
                else:
                    raise ValueError("no usable list in sectors cache")
            else:
                raise ValueError("unexpected sectors cache type")
        except Exception:
            # Fallback to compute_scores if cache unreadable
            score_rows = compute_scores(
                sectors=args.sectors, period=args.period, interval=args.interval
            )
    else:
        score_rows = compute_scores(
            sectors=args.sectors, period=args.period, interval=args.interval
        )

    # Stable asof: derived from input mtimes (so idempotency works).
    def mtime(p: Path) -> int:
        try:
            return int(p.stat().st_mtime)
        except Exception:
            return 0

    snap_epoch = max(
        mtime(pos_p), mtime(sect_cache), (mtime(forecast_p) if forecast_enabled else 0)
    )
    snap_iso = (
        datetime.fromtimestamp(snap_epoch, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
        if snap_epoch > 0
        else utc_now_iso()
    )

    today, swaps_today, state_p = _load_swaps_today()

    # Sectorize positions into the scored universe when needed (stocks/options -> sector ETFs via overrides)
    universe = set()
    for row in score_rows:
        if (
            isinstance(row, dict)
            and isinstance(row.get("symbol"), str)
            and row["symbol"].strip()
        ):
            universe.add(row["symbol"].strip().upper())

    positions_for_rec = positions
    positions_meta = {"mode": "raw", "mapped": [], "unmapped": []}
    try:
        pos2, meta = sectorize_positions(positions, universe)
        # Only use sectorized positions if we actually mapped something into the universe.
        if (
            isinstance(pos2, dict)
            and isinstance(pos2.get("positions"), list)
            and len(pos2["positions"]) > 0
        ):
            positions_for_rec = pos2
            positions_meta = meta
    except Exception:
        pass

    horizon_days = int(getattr(args, "horizon", None) or 5)
    asof_date = datetime.fromisoformat(snap_iso.replace("Z", "+00:00")).date()
    target_trade_date = add_trading_days(asof_date, horizon_days).isoformat()

    computed_at = utc_now_iso()
    sectors_asof = _iso_from_epoch(mtime(sect_cache))

    forecast_asof = (
        forecast_doc.get("snapshot_asof") or forecast_doc.get("asof")
        if isinstance(forecast_doc, dict)
        else None
    )
    forecast_generated_at = (
        forecast_doc.get("generated_at") if isinstance(forecast_doc, dict) else None
    )
    forecast_source_asof = (
        forecast_doc.get("source_asof") if isinstance(forecast_doc, dict) else None
    )

    positions_content_asof = (
        positions.get("asof") if isinstance(positions, dict) else None
    )
    positions_asof = positions_content_asof or positions_asof
    positions_is_fresh = _is_market_session_fresh(
        positions_asof,
        max_age_minutes=int(getattr(args, "max_positions_age_minutes", 15) or 0),
    )

    forecast_freshness_asof = forecast_source_asof or forecast_asof
    forecast_is_fresh = _intraday_fresh_or_last_completed_session(
        forecast_asof,
        int(getattr(args, "max_positions_age_minutes", 15) or 15),
    )

    sectors_is_fresh = _intraday_fresh_or_last_completed_session(
        sectors_asof,
        int(getattr(args, "max_sectors_age_minutes", 15) or 15),
    )

    positions_sha256 = sha256_file(pos_p) if pos_p.exists() else None
    forecast_sha256 = sha256_file(forecast_p) if forecast_p.exists() else None
    sectors_sha256 = sha256_file(sect_cache) if sect_cache.exists() else None

    computation_fingerprint = build_computation_fingerprint(
        snapshot_asof=snap_iso,
        positions_sha256=positions_sha256,
        forecast_sha256=forecast_sha256,
        sectors_sha256=sectors_sha256,
        positions_asof=positions_asof,
        forecast_asof=forecast_asof,
        forecast_source_asof=forecast_source_asof,
        period=args.period,
        interval=args.interval,
        horizon_days=horizon_days,
        forecast_enabled=forecast_enabled,
        positions_mode=positions_meta.get("mode"),
        raw_positions_count=raw_positions_count,
        aggregated_positions_count=aggregated_positions_count,
    )
    snapshot_id = computation_fingerprint[:12]

    if not positions_is_fresh:
        doc: Dict[str, Any] = {
            "schema": "recommendations.v1",
            "snapshot_id": snapshot_id,
            "input_hashes": {
                "positions": positions_sha256,
                "forecast": forecast_sha256,
                "sectors": sectors_sha256,
            },
            "computation_fingerprint": computation_fingerprint,
            "snapshot_asof": snap_iso,
            "asof": snap_iso,
            "generated_at": utc_now_iso(),
            "inputs": {
                "positions_path": str(pos_p),
                "positions_is_fresh": positions_is_fresh,
                "positions_asof": positions_asof,
                "raw_positions_count": raw_positions_count,
                "aggregated_positions_count": aggregated_positions_count,
                "aggregated_positions": aggregated_positions,
                "positions_mtime_epoch": positions_mtime_epoch,
                "max_positions_age_minutes": int(
                    getattr(args, "max_positions_age_minutes", 15) or 0
                ),
                "scores_source": used_source,
                "snapshot_epoch": snap_epoch,
                "period": args.period,
                "interval": args.interval,
                "horizon_trading_days": args.horizon,
                "forecast_mode": bool(forecast_enabled),
                "forecast_status": forecast_status,
                "forecast_path": str(forecast_p),
                "forecast_asof": forecast_asof,
                "forecast_generated_at": forecast_generated_at,
                "forecast_source_asof": forecast_source_asof,
            },
            "recommendation": {
                "action": "NOOP",
                "reason": (
                    "stale_positions_cache: positions.v1.json is too old for "
                    "personalized recommendations; refresh positions first."
                ),
                "horizon_trading_days": horizon_days,
                "target_trade_date": target_trade_date,
                "constraints_applied": ["stale_positions_cache"],
                "diagnostics": {
                    "stale_positions_cache": (not positions_is_fresh),
                    "positions_stale": True,
                    "positions_asof": positions_asof,
                    "positions_mtime_epoch": positions_mtime_epoch,
                    "max_positions_age_minutes": int(
                        getattr(args, "max_positions_age_minutes", 15) or 0
                    ),
                },
            },
        }

        inputs = doc.get("inputs") if isinstance(doc.get("inputs"), dict) else {}

        if not isinstance(inputs, dict):
            inputs = {}

            doc["inputs"] = inputs

        inputs.setdefault("positions_asof", positions_asof)

        inputs.setdefault("positions_mtime_epoch", positions_mtime_epoch)

        inputs.setdefault("forecast_status", forecast_status)

        inputs.setdefault("forecast_path", str(forecast_p))

        inputs.setdefault("forecast_asof", forecast_asof)

        inputs.setdefault("forecast_generated_at", forecast_generated_at)

        inputs.setdefault("forecast_source_asof", forecast_source_asof)

        doc.setdefault("snapshot_id", snapshot_id)

        doc.setdefault("computation_fingerprint", computation_fingerprint)

        doc.setdefault(
            "input_hashes",
            {
                "positions": positions_sha256,
                "forecast": forecast_sha256,
                "sectors": sectors_sha256,
            },
        )

        inputs = doc.get("inputs") if isinstance(doc.get("inputs"), dict) else {}

        if not isinstance(inputs, dict):
            inputs = {}

        doc["inputs"] = inputs

        source_timestamps = (
            doc.get("source_timestamps")
            if isinstance(doc.get("source_timestamps"), dict)
            else {}
        )

        if not isinstance(source_timestamps, dict):
            source_timestamps = {}

        freshness = (
            doc.get("freshness") if isinstance(doc.get("freshness"), dict) else {}
        )

        if not isinstance(freshness, dict):
            freshness = {}

        inputs.setdefault("positions_asof", positions_asof)

        inputs.setdefault("positions_mtime_epoch", positions_mtime_epoch)

        inputs.setdefault("forecast_status", forecast_status)

        inputs.setdefault("forecast_path", str(forecast_p))

        inputs.setdefault("forecast_asof", forecast_asof)

        inputs.setdefault("forecast_generated_at", forecast_generated_at)

        inputs.setdefault("forecast_source_asof", forecast_source_asof)

        inputs.setdefault("sectors_asof", sectors_asof)

        source_timestamps.setdefault("positions_asof", positions_asof)

        source_timestamps.setdefault("forecast_asof", forecast_asof)

        source_timestamps.setdefault("forecast_generated_at", forecast_generated_at)

        source_timestamps.setdefault("forecast_source_asof", forecast_source_asof)

        source_timestamps.setdefault("sectors_asof", sectors_asof)

        source_timestamps.setdefault("snapshot_asof", snap_iso)

        freshness.setdefault("positions_is_fresh", positions_is_fresh)

        freshness.setdefault("forecast_is_fresh", forecast_is_fresh)

        freshness.setdefault("sectors_is_fresh", sectors_is_fresh)

        freshness.setdefault(
            "positions_age_seconds", _age_seconds_from_iso(positions_asof)
        )

        freshness.setdefault(
            "forecast_age_seconds",
            _age_seconds_from_iso(forecast_asof or forecast_source_asof),
        )

        freshness.setdefault("sectors_age_seconds", _age_seconds_from_iso(sectors_asof))

        freshness.setdefault(
            "source_skew_seconds",
            _max_iso_skew_seconds(
                positions_asof,
                forecast_asof,
                forecast_source_asof,
                sectors_asof,
                snap_iso,
            ),
        )

        freshness.setdefault(
            "max_positions_age_minutes",
            int(getattr(args, "max_positions_age_minutes", 15) or 0),
        )

        freshness.setdefault(
            "max_forecast_age_minutes",
            int(getattr(args, "max_forecast_age_minutes", 15) or 0),
        )

        freshness.setdefault(
            "max_sectors_age_minutes",
            int(getattr(args, "max_sectors_age_minutes", 15) or 0),
        )

        doc.setdefault("computed_at", computed_at)

        doc.setdefault("source_timestamps", source_timestamps)

        doc.setdefault("freshness", freshness)

        doc = to_contract(doc)
        changed = atomic_write_json(out_p, doc)

        if not args.quiet:
            print(
                f"OK: wrote recommendations.v1 -> {out_p} "
                f"(changed={changed}) action=NOOP reason=stale_positions_cache"
            )
        return 0

    if not positions_is_fresh:
        rec = SimpleNamespace(
            action="NOOP",
            reason="stale_positions_cache: positions.v1.json is too old for personalized recommendations; refresh positions first.",
            horizon_trading_days=int(args.horizon),
            constraints_applied=["stale_positions_cache"],
            diagnostics={
                "stale_positions_cache": True,
                "positions_asof": positions_asof,
                "positions_is_fresh": positions_is_fresh,
                "max_positions_age_minutes": int(
                    getattr(args, "max_positions_age_minutes", 15) or 0
                ),
            },
            from_symbol=None,
            to_symbol=None,
        )
    else:
        rec = recommend(
            positions=positions_for_rec,
            scores=score_rows,
            constraints={
                "min_improvement_threshold": args.min_improvement,
                "min_delta": args.min_improvement,
                "min_floor": args.min_floor,
                "sgov_symbol": "SGOV",
                "sgov_is_policy_fallback": True,
                "max_precious_holdings": 1,
                "block_gltr_component_overlap": True,
                "forecast_mode": bool(forecast_enabled),
                "forecast_status": forecast_status,
                "forecast_path": str(forecast_p),
                "forecast_asof": forecast_asof,
                "forecast_generated_at": forecast_generated_at,
                "forecast_source_asof": forecast_source_asof,
                "disagreement_veto_edge": args.disagreement_veto_edge,
                "cooldown_trading_days": args.cooldown_trading_days,
                "max_weight_per_symbol": args.max_weight,
                "min_distinct_symbols": args.min_distinct,
                "hhi_cap": args.hhi_cap,
                "horizon_trading_days": args.horizon,
                "max_swaps_per_day": args.max_swaps_per_day,
                "swaps_today": swaps_today,
                "sector_cap": args.sector_cap,
                "turnover_cap": args.turnover_cap,
                # Forecast-mode inputs (Issue #113)
                "forecast_scores": (
                    forecast_doc.get("scores")
                    if isinstance(forecast_doc, dict)
                    else None
                ),
                "forecast_horizons": (
                    forecast_doc.get("horizons_trading_days")
                    if isinstance(forecast_doc, dict)
                    else None
                ),
                "cooldown_history": [],
            },
        )

    # target_trade_date computed above

    doc: Dict[str, Any] = {
        "schema": "recommendations.v1",
        "snapshot_id": snapshot_id,
        "input_hashes": {
            "positions": positions_sha256,
            "forecast": forecast_sha256,
            "sectors": sectors_sha256,
        },
        "computation_fingerprint": computation_fingerprint,
        "snapshot_asof": snap_iso,
        "asof": snap_iso,
        "generated_at": utc_now_iso(),
        "inputs": {
            "positions_path": str(pos_p),
            "positions_mode": positions_meta.get("mode"),
            "positions_mapped": positions_meta.get("mapped"),
            "positions_supported_outside_universe": positions_meta.get(
                "supported_outside_universe"
            ),
            "positions_classified": positions_meta.get("classified"),
            "positions_unmapped": positions_meta.get("unmapped"),
            "positions_asof": positions_asof,
            "positions_is_fresh": positions_is_fresh,
            "max_positions_age_minutes": int(
                getattr(args, "max_positions_age_minutes", 15) or 0
            ),
            "scores_source": used_source,
            "snapshot_epoch": snap_epoch,
            "period": args.period,
            "interval": args.interval,
            "horizon_trading_days": args.horizon,
            "min_improvement_threshold": args.min_improvement,
            "min_delta": args.min_improvement,
            "min_floor": args.min_floor,
            "sgov_symbol": "SGOV",
            "sgov_is_policy_fallback": True,
            "max_precious_holdings": 1,
            "block_gltr_component_overlap": True,
            "forecast_mode": bool(forecast_enabled),
            "forecast_status": forecast_status,
            "forecast_path": str(forecast_p),
            "disagreement_veto_edge": args.disagreement_veto_edge,
            "cooldown_trading_days": args.cooldown_trading_days,
            "max_weight_per_symbol": args.max_weight,
            "min_distinct_symbols": args.min_distinct,
            "hhi_cap": args.hhi_cap,
        },
        "recommendation": {
            "action": rec.action,
            "reason": rec.reason,
            "horizon_trading_days": rec.horizon_trading_days,
            "target_trade_date": target_trade_date,
            "constraints_applied": list(rec.constraints_applied),
            "diagnostics": rec.diagnostics or {},
        },
    }

    if rec.action == "SWAP":
        doc["recommendation"]["from_symbol"] = rec.from_symbol
        doc["recommendation"]["to_symbol"] = rec.to_symbol

    inputs = doc.get("inputs") if isinstance(doc.get("inputs"), dict) else {}

    if not isinstance(inputs, dict):
        inputs = {}

        doc["inputs"] = inputs

    inputs.setdefault("positions_asof", positions_asof)

    inputs.setdefault("positions_mtime_epoch", positions_mtime_epoch)

    inputs.setdefault("forecast_status", forecast_status)

    inputs.setdefault("forecast_path", str(forecast_p))

    inputs.setdefault("forecast_asof", forecast_asof)

    inputs.setdefault("forecast_generated_at", forecast_generated_at)

    inputs.setdefault("forecast_source_asof", forecast_source_asof)

    doc.setdefault("snapshot_id", snapshot_id)

    doc.setdefault("computation_fingerprint", computation_fingerprint)

    doc.setdefault(
        "input_hashes",
        {
            "positions": positions_sha256,
            "forecast": forecast_sha256,
            "sectors": sectors_sha256,
        },
    )

    inputs = doc.get("inputs") if isinstance(doc.get("inputs"), dict) else {}

    if not isinstance(inputs, dict):
        inputs = {}

    doc["inputs"] = inputs

    source_timestamps = (
        doc.get("source_timestamps")
        if isinstance(doc.get("source_timestamps"), dict)
        else {}
    )

    if not isinstance(source_timestamps, dict):
        source_timestamps = {}

    freshness = doc.get("freshness") if isinstance(doc.get("freshness"), dict) else {}

    if not isinstance(freshness, dict):
        freshness = {}

    inputs.setdefault("positions_asof", positions_asof)

    inputs.setdefault("positions_mtime_epoch", positions_mtime_epoch)

    inputs.setdefault("forecast_status", forecast_status)

    inputs.setdefault("forecast_path", str(forecast_p))

    inputs.setdefault("forecast_asof", forecast_asof)

    inputs.setdefault("forecast_generated_at", forecast_generated_at)

    inputs.setdefault("forecast_source_asof", forecast_source_asof)

    inputs.setdefault("sectors_asof", sectors_asof)

    source_timestamps.setdefault("positions_asof", positions_asof)

    source_timestamps.setdefault("forecast_asof", forecast_asof)

    source_timestamps.setdefault("forecast_generated_at", forecast_generated_at)

    source_timestamps.setdefault("forecast_source_asof", forecast_source_asof)

    source_timestamps.setdefault("sectors_asof", sectors_asof)

    source_timestamps.setdefault("snapshot_asof", snap_iso)

    freshness.setdefault("positions_is_fresh", positions_is_fresh)

    freshness.setdefault("forecast_is_fresh", forecast_is_fresh)

    freshness.setdefault("sectors_is_fresh", sectors_is_fresh)

    freshness.setdefault("positions_age_seconds", _age_seconds_from_iso(positions_asof))

    freshness.setdefault(
        "forecast_age_seconds",
        _age_seconds_from_iso(forecast_asof or forecast_source_asof),
    )

    freshness.setdefault("sectors_age_seconds", _age_seconds_from_iso(sectors_asof))

    freshness.setdefault(
        "source_skew_seconds",
        _max_iso_skew_seconds(
            positions_asof, forecast_asof, forecast_source_asof, sectors_asof, snap_iso
        ),
    )

    freshness.setdefault(
        "max_positions_age_minutes",
        int(getattr(args, "max_positions_age_minutes", 15) or 0),
    )

    doc.setdefault("computed_at", computed_at)

    doc.setdefault("source_timestamps", source_timestamps)

    doc.setdefault("freshness", freshness)

    doc = to_contract(doc)
    changed = atomic_write_json(out_p, doc)

    if not args.quiet:
        print(
            f"OK: wrote recommendations.v1 -> {out_p} (changed={changed}) action={rec.action}"
        )

    # M9 ledger: append a recommendation event (best-effort; must not break export)
    try:
        if "doc" in locals():
            from pathlib import Path as _Path

            ledger_db = (
                _Path(getattr(args, "out", "recommendations.v1.json")).resolve().parent
                / "ledger.v0.sqlite"
            )
            ts = doc.get("asof") or doc.get("generated_at")
            append_event(
                db_path=ledger_db,
                event_type="recommendation.v1",
                payload=doc,
                ts_utc=ts if isinstance(ts, str) else None,
            )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
