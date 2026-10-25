"""One score snapshot for Android, the optional prototype and policy CLI; no scoring formula duplication."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import threading
import uuid

from .policy import Scores

_ENGINE_LOCK = threading.RLock()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Scan:
    key: str
    timestamp: str
    rows: tuple[Scores, ...]
    source: str


def scoring_universe(extra=()):
    from .engine import SECTORS_DEFAULT
    from .universe import get_default_scoring_symbols
    from .inverse_universe_v1 import load_inverse_pairs

    inverses = [
        p["inverse"] for p in load_inverse_pairs() if isinstance(p.get("inverse"), str)
    ]
    return sorted(
        set([*SECTORS_DEFAULT, *get_default_scoring_symbols(), *inverses, *extra])
    )


def _complete_payload(payload):
    if not isinstance(payload, dict):
        return False
    cats = payload.get("categories", {})
    for cat in "ABCDE":
        node = cats.get(cat, {})
        checks = node.get("checks", []) if isinstance(node, dict) else []
        if len(checks) != 6 or any(
            type(x.get("score")) not in (int, float) or x["score"] not in (0, 1, 2)
            for x in checks
        ):
            return False
    return True


def rows_from_engine(current, forecasts, *, asof, errors=None):
    from .recommendations_engine import blended_utility_from_scores
    from .alert_snapshots import _compact_state_text_from_structure
    from .forecast_audit import build_symbol_audit_row

    values = blended_utility_from_scores(current, forecast_scores=forecasts)
    out = []
    for row in current:
        sym = row["symbol"]
        by_h = forecasts.get(sym, {})
        h1 = by_h.get(1, by_h.get("1", {}))
        h5 = by_h.get(5, by_h.get("5", {}))
        valid = all(_complete_payload(p) for p in (row, h1, h5))
        meta = values[sym]
        ss = h5.get("structure_summary") or h1.get("structure_summary") or {}

        def pct(name):
            v = meta.get(name)
            return round(v * 100, 8) if valid and isinstance(v, (int, float)) else None

        audit = build_symbol_audit_row(
            symbol=sym, asof=asof, current_payload=row, h1_payload=h1, h5_payload=h5
        )
        glyph = " ".join(audit.canonical_tokens.values()) if audit.all_valid else ""
        out.append(
            Scores(
                sym,
                pct("current_utility"),
                pct("h1_utility"),
                pct("h5_utility"),
                pct("utility"),
                _compact_state_text_from_structure(ss) or "",
                ss.get("price"),
                ss.get("tactical_stop_candidate"),
                ss.get("stop_buy_candidate"),
                asof,
                (errors or {}).get(sym, "")
                or ("" if valid else "Incomplete engine checks/forecasts."),
                glyph,
            )
        )
    return tuple(out)


def calculate_frames(frames, symbols, *, asof, calendar=None, errors=None):
    """Calculate from explicit OHLCV. This interface never downloads market data.

    Both Android and CLI use the existing current/forecast/structure/GlyphSpec
    functions here. All optional scoring inputs belong in the input contract.
    """
    from . import engine
    from .forecast_features import OHLCV
    from .forecast_score_provider import compute_forecast_universe
    from dataclasses import replace
    import pandas as pd

    order = list(dict.fromkeys(symbols))
    if not order:
        raise ValueError("The scoring universe must not be empty.")
    errors = dict(errors or {})
    ohlcv = {}
    for sym, frame in frames.items():
        columns = ("Close", "High", "Low", "Volume")
        if frame is None or not all(c in frame for c in columns):
            errors[sym] = "Market data missing required OHLCV fields."
            continue
        cleaned = frame[list(columns)].dropna()
        if (
            len(cleaned) < 60
            or len(cleaned) != len(frame)
            or any(not math.isfinite(float(x)) for x in cleaned.to_numpy().flat)
        ):
            errors[sym] = "Market data needs at least 60 complete finite bars."
            continue
        ohlcv[sym] = OHLCV(
            close=cleaned.Close.tolist(),
            high=cleaned.High.tolist(),
            low=cleaned.Low.tolist(),
            volume=cleaned.Volume.tolist(),
        )
    if "SPY" not in ohlcv or "^VIX" not in ohlcv:
        raise RuntimeError(
            "Required SPY/VIX market data unavailable; previous results are stale."
        )
    valid = [s for s in order if s in ohlcv]
    if not valid:
        raise RuntimeError("No symbols returned complete market data.")
    with _ENGINE_LOCK:
        previous_cache = dict(engine._DOWNLOAD_CACHE)
        previous_fn = engine._DOWNLOAD_FN
        engine._DOWNLOAD_CACHE.clear()
        try:
            current = engine.compute_scores(
                sectors=valid,
                ttl_sec=0,
                download_fn=lambda ticker, **kw: frames.get(ticker, pd.DataFrame()),
            )
            forecasts = compute_forecast_universe(
                universe={s: ohlcv[s] for s in valid},
                spy=ohlcv["SPY"],
                vix_close=ohlcv["^VIX"].close,
                horizons_trading_days=(1, 5),
                calendar=calendar,
            )
            result = list(rows_from_engine(current, forecasts, asof=asof))
            for i, score in enumerate(result):
                result[i] = replace(
                    score,
                    price=float(ohlcv[score.symbol].close[-1]),
                    asof=str(frames[score.symbol].index[-1]),
                )
            result.extend(
                Scores(s, asof=asof, error=errors.get(s, "No market data."))
                for s in order
                if s not in valid
            )
            return tuple(result)
        finally:
            engine._DOWNLOAD_CACHE.clear()
            engine._DOWNLOAD_CACHE.update(previous_cache)
            engine._DOWNLOAD_FN = previous_fn


def live_scan(symbols=None, *, download_fn=None):
    from . import engine

    order = list(symbols or scoring_universe())
    with _ENGINE_LOCK:
        previous_cache = dict(engine._DOWNLOAD_CACHE)
        previous_fn = engine._DOWNLOAD_FN
        engine._DOWNLOAD_CACHE.clear()
        engine._DOWNLOAD_FN = download_fn
        try:
            frames = engine.safe_download(
                sorted(set(order + ["SPY", "^VIX"])), ttl_sec=0
            )
            timestamp = utc_now()
            rows = calculate_frames(frames, order, asof=timestamp)
            return Scan(uuid.uuid4().hex, timestamp, rows, "live engine")
        finally:
            engine._DOWNLOAD_CACHE.clear()
            engine._DOWNLOAD_CACHE.update(previous_cache)
            engine._DOWNLOAD_FN = previous_fn


def snapshot_scan(path):
    """Explicit local input; never read ownership or recommendations from artifacts."""
    raw = Path(path).read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or not isinstance(doc.get("asof"), str):
        raise ValueError(
            "Snapshot requires an asof timestamp and rows or data.sectors."
        )
    datetime.fromisoformat(doc["asof"].replace("Z", "+00:00"))
    if "rows" in doc:
        names = set(Scores.__dataclass_fields__)
        rows = tuple(
            Scores(**{k: v for k, v in row.items() if k in names})
            for row in doc["rows"]
        )
    else:
        data = doc.get("data", doc)
        rows = rows_from_engine(
            data.get("sectors", []),
            data.get("forecast_scores", {}).get("scores", {}),
            asof=doc["asof"],
        )
    if not rows or len({s.symbol for s in rows}) != len(rows):
        raise ValueError("Snapshot must contain nonempty unique symbol rows.")
    return Scan(
        hashlib.sha256(raw).hexdigest(),
        doc["asof"],
        rows,
        "local snapshot (historical)",
    )


def calculate_document(document):
    """Portable JSON input contract used by Android and fixture/CLI callers."""
    from .data.ohlcv import frames_from_document, frames_from_charts

    if "charts" in document:
        frames, errors = frames_from_charts(document)
    else:
        frames, errors = frames_from_document(document), document.get("errors", {})
    return calculate_frames(
        frames,
        document["symbols"],
        asof=document["asof"],
        calendar=document.get("calendar", {}),
        errors=errors,
    )
