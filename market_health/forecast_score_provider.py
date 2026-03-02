"""
forecast_score_provider.py

Thin orchestrator for forecast-mode scoring.
Computes features from OHLCV and delegates 0/1/2 scoring to A–E modules (6 checks each).
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import json
from typing import Any, Dict, Optional, Sequence, Union
from .forecast_features import (
    OHLCV,
    atr_percent,
    bollinger_bands,
    close_location_value,
    cross_sectional_dispersion,
    normalized_slope,
    pct_change,
    rolling_correlation,
    rolling_max,
    rolling_min,
    rolling_percentile_rank,
    rs_ratio,
    sma,
    up_down_volume_ratio,
    zscore,
    ema,
)
from .forecast_types import category_dict
from .forecast_checks_a_announcements import compute_a_checks
from .forecast_checks_b_backdrop import compute_b_checks
from .forecast_checks_c_crowding import compute_c_checks
from .forecast_checks_d_danger import compute_d_checks
from .forecast_checks_e_environment import compute_e_checks


CAL_PATH = Path.home() / ".cache" / "jerboa" / "calendar.v1.json"


@lru_cache(maxsize=1)
def _load_calendar_v1() -> object:
    try:
        if CAL_PATH.exists():
            return json.loads(CAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _calendar_ctx_for_symbol(calendar: object, sym: str, H: int) -> object:
    """
    Build a symbol-aware calendar context for forecast checks.

    Recommended policy:
      - ignore global-only catalysts (symbol="") for per-symbol relative scoring
      - only set catalysts_in_window True if sym is explicitly listed
    """
    if calendar is None:
        calendar = _load_calendar_v1()
    if not isinstance(calendar, dict):
        return calendar

    cal = calendar
    # If passed a full calendar.v1 doc, pick the horizon window.
    if "windows" in cal and isinstance(cal.get("windows"), dict):
        by_h = (cal.get("windows") or {}).get("by_h")
        if isinstance(by_h, dict):
            win = by_h.get(str(int(H)))
            if isinstance(win, dict):
                cal = win

    if not isinstance(cal, dict):
        return calendar

    ctx = dict(cal)
    sym_u = (sym or "").strip().upper()
    ctx["symbol"] = sym_u

    # Prefer calendar window bucket: ctx["catalyst"] = {"count":..., "symbols":[...]}
    cat = ctx.get("catalyst")
    if isinstance(cat, dict):
        syms = cat.get("symbols") if isinstance(cat.get("symbols"), list) else []
        cnt = int(cat.get("count", 0) or 0)
    else:
        syms = (
            ctx.get("catalyst_symbols_in_window")
            if isinstance(ctx.get("catalyst_symbols_in_window"), list)
            else []
        )
        cnt = int(ctx.get("catalysts_count_in_window", 0) or 0)

    syms_u = {s.strip().upper() for s in syms if isinstance(s, str) and s.strip()}
    ctx["catalyst_symbols_in_window"] = list(syms)
    ctx["catalysts_count_in_window"] = cnt

    # Symbol-specific in-window
    ctx["catalysts_in_window"] = bool(sym_u and sym_u in syms_u)

    # If there are catalysts but no symbols listed, treat as global-only and IGNORE for per-symbol scoring.
    if cnt > 0 and not syms_u:
        ctx["catalysts_in_window"] = False
        ctx["global_catalysts_in_window"] = True
    else:
        ctx["global_catalysts_in_window"] = False

    return ctx


Number = Union[int, float]


def compute_forecast_universe(
    *,
    universe: Dict[str, OHLCV],
    spy: OHLCV,
    horizons_trading_days: Sequence[int] = (1, 5),
    vix_close: Optional[Sequence[Number]] = None,
    calendar: Optional[Dict[str, Any]] = None,
    policy: Optional[Dict[str, Any]] = None,
    flow_by_symbol: Optional[Dict[str, Dict[str, float]]] = None,
    flow_status: Optional[str] = None,
    iv_by_symbol: Optional[Dict[str, Dict[str, float]]] = None,
    iv_status: Optional[str] = None,
) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """
    Returns results[symbol][H] with:
      - forecast_score (0..1)
      - points/max_points
      - categories A–E (each includes 6 checks)
      - diagnostics (metrics)
    """
    horizons = [int(h) for h in horizons_trading_days] or [1]
    _ = policy  # reserved for future use

    # Precompute returns for dispersion/correlation
    returns_by_symbol: Dict[str, list[Optional[float]]] = {
        s.upper(): pct_change(ohlcv.close) for s, ohlcv in universe.items()
    }
    spy_returns = pct_change(spy.close)

    # Optional VIX features
    vix_features: Dict[str, Any] = {}
    if vix_close is not None:
        vix_c = [float(x) for x in vix_close]
        vix_features["vix_slope_10"] = normalized_slope(vix_c, 10)
        vix_features["vix_rank_60"] = rolling_percentile_rank(vix_c, 60)

    spy_close = [float(x) for x in spy.close]
    spy_slope_10 = normalized_slope(spy_close, 10)
    spy_slope_10_now = spy_slope_10[-1] if spy_slope_10 else None

    results: Dict[str, Dict[int, Dict[str, Any]]] = {}

    for sym, ohlcv in universe.items():
        sym_u = sym.upper()
        close = [float(x) for x in ohlcv.close]
        n = len(close)
        idx = n - 1

        if n == 0:
            results[sym_u] = {
                h: {
                    "forecast_score": 0.0,
                    "points": 0,
                    "max_points": 0,
                    "categories": {},
                    "diagnostics": {"note": "empty_series"},
                }
                for h in horizons
            }
            continue

        # Shared features at "now"
        bb = bollinger_bands(close, 20, 2.0)
        bb_width = bb["width_pct"][idx] if idx < len(bb["width_pct"]) else None
        ext_z = zscore(close, 20)
        ext_z_now = ext_z[idx] if idx < len(ext_z) else None

        rs = rs_ratio(close, spy.close)
        rs_f = [x if x is not None else 0.0 for x in rs]
        rs_slope_10 = normalized_slope(rs_f, 10)
        rs_slope_10_now = rs_slope_10[idx] if idx < len(rs_slope_10) else None
        rs_z_20 = zscore(rs_f, 20)
        rs_z_20_now = rs_z_20[idx] if idx < len(rs_z_20) else None

        corr20 = rolling_correlation(returns_by_symbol.get(sym_u, []), spy_returns, 20)
        corr5 = rolling_correlation(returns_by_symbol.get(sym_u, []), spy_returns, 5)
        corr20_now = corr20[idx] if idx < len(corr20) else None
        corr5_now = corr5[idx] if idx < len(corr5) else None

        dispersion_now = cross_sectional_dispersion(returns_by_symbol, idx)

        ema20 = ema(
            close, 20
        )  # SMA is fine as proxy for the orchestrator; check modules don't care
        sma50 = sma(close, 50)
        ema20_now = ema20[idx] if idx < len(ema20) else None
        sma50_now = sma50[idx] if idx < len(sma50) else None

        slope_close_10 = normalized_slope(close, 10)
        slope_close_10_now = slope_close_10[idx] if idx < len(slope_close_10) else None

        hi20 = rolling_max(close, 20)
        hi20_now = hi20[idx] if idx < len(hi20) else None

        lo20 = rolling_min(close, 20)
        lo20_now = lo20[idx] if idx < len(lo20) else None

        # ATR% and CLV
        atrp14_now = None
        atrp_slope_10_now = None
        clv_now = None
        if ohlcv.high is not None and ohlcv.low is not None:
            atrp = atr_percent(ohlcv.high, ohlcv.low, close, 14)
            atrp14_now = atrp[idx] if idx < len(atrp) else None
            atrp_slope_10 = normalized_slope(
                [x if x is not None else 0.0 for x in atrp], 10
            )
            atrp_slope_10_now = atrp_slope_10[idx] if idx < len(atrp_slope_10) else None
            clv = close_location_value(ohlcv.high, ohlcv.low, close)
            clv_now = clv[idx] if idx < len(clv) else None

        # Volume proxies
        updn_now = None
        vol_rank_now = None
        if ohlcv.volume is not None:
            updn = up_down_volume_ratio(close, ohlcv.volume, 20)
            updn_now = updn[idx] if idx < len(updn) else None
            vol_rank = rolling_percentile_rank([float(v) for v in ohlcv.volume], 20)
            vol_rank_now = vol_rank[idx] if idx < len(vol_rank) else None

        last_ret = (
            returns_by_symbol.get(sym_u, [None])[idx]
            if sym_u in returns_by_symbol and idx < len(returns_by_symbol[sym_u])
            else None
        )

        results[sym_u] = {}

        for H in horizons:
            # Dimension modules (exactly 6 each)
            a_checks = compute_a_checks(
                horizon_days=H,
                calendar=_calendar_ctx_for_symbol(calendar, sym, H),
                vix_features=vix_features,
                ext_z=ext_z_now,
                bb_width=bb_width,
                atrp14=atrp14_now,
                rs_slope_10=rs_slope_10_now,
                returns=returns_by_symbol.get(sym_u),
            )

            b_checks = compute_b_checks(
                horizon_days=H, close=close[idx],
                ema20=ema20_now,
                sma50=sma50_now,
                slope_close_10=slope_close_10_now,
                hi20=hi20_now,
                clv=clv_now,
                rs_slope_10=rs_slope_10_now,
                rs_z_20=rs_z_20_now,
                atrp14=atrp14_now,
                up_down_vol_ratio_20=updn_now,
                ext_z_20=ext_z_now,
                vol_rank_20=vol_rank_now,
            )

            support_cushion_proxy = (
                b_checks[3].metrics.get("cushion_proxy") if len(b_checks) >= 4 else None
            )

            c_checks = compute_c_checks(
                horizon_days=H, ext_z_20=ext_z_now,
                vol_rank_20=vol_rank_now,
                last_ret=last_ret,
                clv=clv_now,
                returns=returns_by_symbol.get(sym_u),
                up_down_vol_ratio_20=updn_now,
                corr20=corr20_now,
                dispersion=dispersion_now,
                flow_metrics=(flow_by_symbol.get(sym_u) if flow_by_symbol else None),
                flow_status=flow_status,
            )

            d_checks = compute_d_checks(
                horizon_days=H,
                atrp14=atrp14_now,
                atrp_slope_10=atrp_slope_10_now,
                bb_width=bb_width,
                returns=returns_by_symbol.get(sym_u),
                calendar=_calendar_ctx_for_symbol(calendar, sym, H),
                corr5=corr5_now,
                corr20=corr20_now,
                volume=ohlcv.volume,
                close=close[idx],
                lo20=lo20_now,
                support_cushion_proxy=support_cushion_proxy,
                iv=(iv_by_symbol.get(sym_u, {}).get("iv") if iv_by_symbol else None),
                iv_rank_1y=(
                    iv_by_symbol.get(sym_u, {}).get("iv_rank_1y")
                    if iv_by_symbol
                    else None
                ),
                iv_percentile_1y=(
                    iv_by_symbol.get(sym_u, {}).get("iv_percentile_1y")
                    if iv_by_symbol
                    else None
                ),
                iv_status=iv_status,
            )

            e_checks = compute_e_checks(
                horizon_days=H, symbol=sym_u,
                spy_slope_10=spy_slope_10_now,
                vix_features=vix_features,
                returns_by_symbol=returns_by_symbol,
                dispersion=dispersion_now,
                rs_slope_10=rs_slope_10_now,
            )

            categories = {
                "A": category_dict(a_checks, horizon_days=int(H)),
                "B": category_dict(b_checks, horizon_days=int(H)),
                "C": category_dict(c_checks, horizon_days=int(H)),
                "D": category_dict(d_checks, horizon_days=int(H)),
                "E": category_dict(e_checks, horizon_days=int(H)),
            }

            total_points = sum(categories[k]["points"] for k in categories)
            total_max = sum(categories[k]["max_points"] for k in categories)
            forecast_score = (total_points / total_max) if total_max else 0.0

            diagnostics = {
                "H": H,
                "idx": idx,
                "close": close[idx],
                "bb_width": bb_width,
                "ext_z_20": ext_z_now,
                "atrp14": atrp14_now,
                "atrp_slope_10": atrp_slope_10_now,
                "rs_slope_10": rs_slope_10_now,
                "corr20": corr20_now,
                "dispersion": dispersion_now,
                "vol_rank_20": vol_rank_now,
                "calendar_present": calendar is not None,
                "vix_present": bool(vix_features),
            }

            results[sym_u][H] = {
                "forecast_score": forecast_score,
                "points": total_points,
                "max_points": total_max,
                "categories": categories,
                "diagnostics": diagnostics,
            }

    return results
