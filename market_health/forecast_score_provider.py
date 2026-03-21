"""
forecast_score_provider.py

Thin orchestrator for forecast-mode scoring.
Computes features from OHLCV and delegates 0/1/2 scoring to A–E modules (6 checks each).
"""

from __future__ import annotations

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
from .structure_engine import compute_structure_summary, empty_structure_summary

Number = Union[int, float]


def _structure_context_for_ohlcv(
    *,
    close: Sequence[float],
    ohlcv: OHLCV,
    idx: int,
    atrp14_now: Optional[float],
) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "timeframe": "1d",
        "closes": list(close),
    }

    if ohlcv.high is not None and ohlcv.low is not None:
        highs = [float(x) for x in ohlcv.high]
        lows = [float(x) for x in ohlcv.low]
        if len(highs) == len(close) and len(lows) == len(close):
            context["highs"] = highs
            context["lows"] = lows
            if idx >= 1:
                context["previous_bar"] = {
                    "high": highs[idx - 1],
                    "low": lows[idx - 1],
                    "close": close[idx - 1],
                }

    if ohlcv.volume is not None:
        volumes = [float(v) for v in ohlcv.volume]
        if len(volumes) == len(close):
            context["prices"] = list(close)
            context["volumes"] = volumes

    if atrp14_now is not None:
        atr_now = (float(close[idx]) * float(atrp14_now)) / 100.0
        if atr_now > 0:
            context["atr"] = atr_now

    return context


def _compute_structure_sidecar(
    *,
    symbol: str,
    close: Sequence[float],
    ohlcv: OHLCV,
    idx: int,
    atrp14_now: Optional[float],
) -> Dict[str, Any]:
    try:
        return compute_structure_summary(
            symbol,
            price=float(close[idx]),
            context=_structure_context_for_ohlcv(
                close=close,
                ohlcv=ohlcv,
                idx=idx,
                atrp14_now=atrp14_now,
            ),
        ).to_dict()
    except Exception as exc:
        fallback = empty_structure_summary(symbol, price=float(close[idx])).to_dict()
        fallback["notes"] = [
            *list(fallback.get("notes") or []),
            f"error={exc.__class__.__name__}",
        ]
        return fallback


def _has_zone_levels(zone: Any) -> bool:
    return isinstance(zone, dict) and any(
        zone.get(k) is not None for k in ("lower", "center", "upper")
    )


def _structure_explainability(structure_summary: Dict[str, Any]) -> Dict[str, Any]:
    has_levels = _has_zone_levels(
        structure_summary.get("nearest_support_zone")
    ) or _has_zone_levels(structure_summary.get("nearest_resistance_zone"))

    return {
        "structure_sidecar_version": structure_summary.get("version"),
        "structure_has_levels": has_levels,
        "structure_no_edge": not has_levels,
        "structure_state_tags": list(structure_summary.get("state_tags") or []),
        "structure_notes": list(structure_summary.get("notes") or []),
    }


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

        structure_summary = _compute_structure_sidecar(
            symbol=sym_u,
            close=close,
            ohlcv=ohlcv,
            idx=idx,
            atrp14_now=atrp14_now,
        )
        explainability = _structure_explainability(structure_summary)

        results[sym_u] = {}

        for H in horizons:
            # Dimension modules (exactly 6 each)
            a_checks = compute_a_checks(
                H=H,
                calendar=calendar,
                vix_features=vix_features,
                ext_z=ext_z_now,
                bb_width=bb_width,
                atrp14=atrp14_now,
                rs_slope_10=rs_slope_10_now,
                returns=returns_by_symbol.get(sym_u),
            )

            b_checks = compute_b_checks(
                close=close[idx],
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
                ext_z_20=ext_z_now,
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
                H=H,
                atrp14=atrp14_now,
                atrp_slope_10=atrp_slope_10_now,
                bb_width=bb_width,
                returns=returns_by_symbol.get(sym_u),
                calendar=calendar,
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
                symbol=sym_u,
                spy_slope_10=spy_slope_10_now,
                vix_features=vix_features,
                returns_by_symbol=returns_by_symbol,
                dispersion=dispersion_now,
                rs_slope_10=rs_slope_10_now,
            )

            categories = {
                "A": category_dict(a_checks),
                "B": category_dict(b_checks),
                "C": category_dict(c_checks),
                "D": category_dict(d_checks),
                "E": category_dict(e_checks),
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
                "structure_summary": structure_summary,
                "explainability": explainability,
            }

    return results
