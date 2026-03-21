from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Tuple

from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe
from market_health.recommendations_engine import Recommendation, recommend


def _ohlcv_trend(n: int = 90, *, direction: int = 1, step: float = 0.25) -> OHLCV:
    """Deterministic synthetic OHLCV. direction=+1 up, -1 down."""
    base = 100.0
    close = [base + direction * (i * step) for i in range(n)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    volume = [1_000_000.0 for _ in close]
    return OHLCV(close=close, high=high, low=low, volume=volume)


def _round_f(x: Any, nd: int = 6) -> Any:
    if isinstance(x, float):
        return round(x, nd)
    return x


def _sanitize_forecast(
    scores: Mapping[str, Any], symbols: Iterable[str]
) -> Dict[str, Any]:
    """
    Make fixture stable:
    - keep forecast_score/points/max_points
    - keep A–E checks with only label + score
    - drop metrics/meaning to avoid churn
    """
    out: Dict[str, Any] = {}
    for sym in [s.upper() for s in symbols]:
        by_h = scores.get(sym)
        if not isinstance(by_h, dict):
            continue

        sym_out: Dict[str, Any] = {}
        for hk, payload in by_h.items():
            try:
                h = int(hk)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue

            cats = payload.get("categories")
            cats = cats if isinstance(cats, dict) else {}

            structure = payload.get("structure_summary")
            structure = structure if isinstance(structure, dict) else {}

            explainability = payload.get("explainability")
            explainability = explainability if isinstance(explainability, dict) else {}

            slim_cats: Dict[str, Any] = {}
            for k in ("A", "B", "C", "D", "E"):
                cat = cats.get(k)
                if not isinstance(cat, dict):
                    slim_cats[k] = {"checks": []}
                    continue
                checks = cat.get("checks")
                checks = checks if isinstance(checks, list) else []
                slim_cats[k] = {
                    "checks": [
                        {
                            "label": str(chk.get("label", "")),
                            "score": int(chk.get("score", 0) or 0),
                        }
                        for chk in checks
                        if isinstance(chk, dict)
                    ]
                }

            sym_out[str(h)] = {
                "forecast_score": _round_f(float(payload.get("forecast_score", 0.0))),
                "points": int(payload.get("points", 0) or 0),
                "max_points": int(payload.get("max_points", 0) or 0),
                "categories": slim_cats,
                "structure_summary": {
                    "version": str(structure.get("version", "")),
                    "support_cushion_atr": _round_f(
                        structure.get("support_cushion_atr")
                    ),
                    "overhead_resistance_atr": _round_f(
                        structure.get("overhead_resistance_atr")
                    ),
                    "breakout_quality_bucket": structure.get("breakout_quality_bucket"),
                    "breakdown_risk_bucket": structure.get("breakdown_risk_bucket"),
                    "state_tags": list(structure.get("state_tags") or []),
                    "notes": list(structure.get("notes") or []),
                },
                "explainability": {
                    "structure_sidecar_version": explainability.get(
                        "structure_sidecar_version"
                    ),
                    "structure_has_levels": bool(
                        explainability.get("structure_has_levels", False)
                    ),
                    "structure_no_edge": bool(
                        explainability.get("structure_no_edge", False)
                    ),
                    "structure_state_tags": list(
                        explainability.get("structure_state_tags") or []
                    ),
                },
            }

        if sym_out:
            out[sym] = sym_out
    return out


def _sanitize_rec(rec: Recommendation) -> Dict[str, Any]:
    diag = rec.diagnostics or {}
    edges_by_h = diag.get("edges_by_h")
    if not isinstance(edges_by_h, dict):
        edges_by_h = {}

    return {
        "action": rec.action,
        "from_symbol": rec.from_symbol,
        "to_symbol": rec.to_symbol,
        "reason": rec.reason,
        "constraints_applied": list(rec.constraints_applied),
        "constraints_triggered": list(rec.constraints_triggered),
        "diagnostics": {
            "mode": diag.get("mode"),
            "decision_metric": diag.get("decision_metric"),
            "edge": _round_f(diag.get("edge")),
            "robust_edge": _round_f(diag.get("robust_edge")),
            "edges_by_h": {str(k): _round_f(v) for k, v in edges_by_h.items()},
        },
    }


def build_universe() -> Tuple[Dict[str, OHLCV], list[str]]:
    # 11 sector ETFs + SPY
    syms = [
        "SPY",
        "XLB",
        "XLC",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLRE",
        "XLU",
        "XLV",
        "XLY",
    ]

    # Make one clear winner (XLE) and make two held symbols weaker (XLK, XLF)
    universe: Dict[str, OHLCV] = {}
    for s in syms:
        if s == "SPY":
            universe[s] = _ohlcv_trend(direction=1, step=0.20)
        elif s == "XLE":
            universe[s] = _ohlcv_trend(direction=1, step=0.40)
        elif s in {"XLK", "XLF"}:
            universe[s] = _ohlcv_trend(direction=-1, step=0.25)
        else:
            universe[s] = _ohlcv_trend(direction=-1, step=0.10)

    return universe, syms


def generate_golden_fixtures_v1() -> Dict[str, Any]:
    universe, syms = build_universe()

    # compute_forecast_universe returns: {SYM: {H: payload}}
    scores = compute_forecast_universe(
        universe=universe,
        spy=universe["SPY"],
        horizons_trading_days=(1, 5),
    )

    forecast_fixture = {
        "schema": "golden.forecast_scores.v1",
        "horizons_trading_days": [1, 5],
        "symbols": syms,
        "scores": _sanitize_forecast(scores, syms),
    }

    # Forecast-mode recommend() path (pass scores=[], it won’t be used in forecast mode)
    positions = {
        "schema": "positions.v1",
        "positions": [
            {"symbol": "XLK", "market_value": 1000.0},
            {"symbol": "XLF", "market_value": 1000.0},
        ],
    }

    rec = recommend(
        positions=positions,
        scores=[],
        constraints={
            "forecast_scores": scores,
            "forecast_horizons": (1, 5),
            "min_improvement_threshold": 0.12,
            "disagreement_veto_edge": 0.0,
            "cooldown_trading_days": 0,
            "cooldown_history": [],
            # Relax diversity so we actually exercise the SWAP path deterministically
            "max_weight_per_symbol": 1.0,
            "min_distinct_symbols": 1,
            "hhi_cap": 1.0,
            "max_swaps_per_day": 1,
            "swaps_today": 0,
        },
    )

    rec_fixture = {
        "schema": "golden.recommendation.forecast.v1",
        "positions": positions,
        "recommendation": _sanitize_rec(rec),
    }

    return {"forecast": forecast_fixture, "recommendation": rec_fixture}
