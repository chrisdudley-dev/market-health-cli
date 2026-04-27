#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

from market_health.etf_universe_v1 import load_etf_universe


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _country_symbols() -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for row in load_etf_universe():
        if not isinstance(row, dict):
            continue
        if row.get("family") != "global_broad_market":
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if sym and sym not in seen and bool(row.get("enabled", True)):
            seen.add(sym)
            out.append(sym)

    return out


def _forecast_score_for_horizon(row: Any, horizon: int) -> float | None:
    if not isinstance(row, dict):
        return None

    candidates = [
        row.get(str(horizon)),
        row.get(horizon),
        row.get(f"H{horizon}"),
        row.get(f"h{horizon}"),
    ]

    for candidate in candidates:
        if isinstance(candidate, dict):
            val = (
                candidate.get("forecast_score")
                or candidate.get("score")
                or candidate.get("blend")
            )
            if isinstance(val, (int, float)):
                return float(val)
        elif isinstance(candidate, (int, float)):
            return float(candidate)

    # Some payloads may flatten H1/H5 directly.
    for key in (f"forecast_h{horizon}", f"h{horizon}", f"H{horizon}"):
        val = row.get(key)
        if isinstance(val, (int, float)):
            return float(val)

    return None


def _load_forecast_scores(
    path: Path, symbols: list[str]
) -> dict[str, dict[str, float | None]]:
    doc = _read_json(path)
    scores = doc.get("scores")
    if not isinstance(scores, dict):
        return {}

    out: dict[str, dict[str, float | None]] = {}
    wanted = set(symbols)

    for sym, row in scores.items():
        if not isinstance(sym, str):
            continue
        sym_u = sym.upper()
        if sym_u not in wanted:
            continue

        out[sym_u] = {
            "h1": _forecast_score_for_horizon(row, 1),
            "h5": _forecast_score_for_horizon(row, 5),
        }

    return out


def _download_prices(symbols: list[str], period: str) -> dict[str, list[float]]:
    if yf is None:
        raise RuntimeError("yfinance is not available in this environment")

    if not symbols:
        return {}

    data = yf.download(
        tickers=symbols,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="ticker",
    )

    out: dict[str, list[float]] = {}

    if data is None or getattr(data, "empty", False):
        return out

    if getattr(data.columns, "nlevels", 1) > 1:
        for sym in symbols:
            sym_u = sym.upper()
            try:
                frame = data[sym_u]
            except Exception:
                continue
            if "Close" not in frame:
                continue
            vals = [float(v) for v in frame["Close"].tolist() if v == v]
            if len(vals) >= 22:
                out[sym_u] = vals
        return out

    # Single-symbol fallback.
    if len(symbols) == 1 and "Close" in data:
        vals = [float(v) for v in data["Close"].tolist() if v == v]
        if len(vals) >= 22:
            out[symbols[0].upper()] = vals

    return out


def _return_from_tail(close: list[float], days: int) -> float | None:
    if len(close) <= days:
        return None
    start = close[-days - 1]
    end = close[-1]
    if start == 0:
        return None
    return (end / start) - 1.0


def _rank(values: dict[str, float], *, reverse: bool = True) -> dict[str, int]:
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=reverse)
    return {sym: i + 1 for i, (sym, _) in enumerate(ordered)}


def _spearman(a: dict[str, float], b: dict[str, float]) -> float | None:
    common = sorted(set(a) & set(b))
    if len(common) < 3:
        return None

    ra = _rank({sym: a[sym] for sym in common}, reverse=True)
    rb = _rank({sym: b[sym] for sym in common}, reverse=True)

    n = len(common)
    d2 = sum((ra[sym] - rb[sym]) ** 2 for sym in common)
    denom = n * ((n * n) - 1)
    if denom == 0:
        return None
    return 1.0 - ((6.0 * d2) / denom)


def _fmt_pct(x: float | None) -> str:
    if x is None or not math.isfinite(x):
        return "-"
    return f"{x * 100:.1f}%"


def _fmt_score(x: float | None) -> str:
    if x is None or not math.isfinite(x):
        return "-"
    return f"{x * 100:.0f}%"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate global broad-market ETF H1/H5 forecast behavior."
    )
    ap.add_argument(
        "--forecast",
        default=os.path.expanduser("~/.cache/jerboa/forecast_scores.v1.json"),
        help="Path to forecast_scores.v1.json",
    )
    ap.add_argument(
        "--period",
        default="6mo",
        help="yfinance history period to download for realized-return comparison",
    )
    ap.add_argument(
        "--out-dir",
        default=os.path.expanduser("~/.cache/jerboa/reports"),
        help="Directory for Markdown/CSV report output",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top rows to show in Markdown report",
    )
    args = ap.parse_args()

    forecast_path = Path(args.forecast).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    symbols = _country_symbols()
    forecast = _load_forecast_scores(forecast_path, symbols)

    missing_forecast = sorted(set(symbols) - set(forecast))

    prices = _download_prices(symbols, period=str(args.period))
    missing_prices = sorted(set(symbols) - set(prices))

    rows: list[dict[str, Any]] = []

    for sym in symbols:
        h1 = forecast.get(sym, {}).get("h1")
        h5 = forecast.get(sym, {}).get("h5")
        close = prices.get(sym) or []

        r1 = _return_from_tail(close, 1)
        r5 = _return_from_tail(close, 5)
        r20 = _return_from_tail(close, 20)

        rows.append(
            {
                "symbol": sym,
                "h1_score": h1,
                "h5_score": h5,
                "realized_1d": r1,
                "realized_5d": r5,
                "realized_20d": r20,
            }
        )

    h1_scores = {
        str(r["symbol"]): float(r["h1_score"])
        for r in rows
        if isinstance(r.get("h1_score"), (int, float))
    }
    h5_scores = {
        str(r["symbol"]): float(r["h5_score"])
        for r in rows
        if isinstance(r.get("h5_score"), (int, float))
    }
    r1_values = {
        str(r["symbol"]): float(r["realized_1d"])
        for r in rows
        if isinstance(r.get("realized_1d"), (int, float))
    }
    r5_values = {
        str(r["symbol"]): float(r["realized_5d"])
        for r in rows
        if isinstance(r.get("realized_5d"), (int, float))
    }
    r20_values = {
        str(r["symbol"]): float(r["realized_20d"])
        for r in rows
        if isinstance(r.get("realized_20d"), (int, float))
    }

    h1_vs_1d = _spearman(h1_scores, r1_values)
    h5_vs_5d = _spearman(h5_scores, r5_values)
    h5_vs_20d = _spearman(h5_scores, r20_values)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"global_broad_market_forecast_validation_{stamp}.csv"
    md_path = out_dir / f"global_broad_market_forecast_validation_{stamp}.md"

    sorted_rows = sorted(
        rows,
        key=lambda r: (
            r["h5_score"] if isinstance(r.get("h5_score"), (int, float)) else -1.0
        ),
        reverse=True,
    )

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "h1_score",
                "h5_score",
                "realized_1d",
                "realized_5d",
                "realized_20d",
            ],
        )
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow(row)

    lines = [
        "# Global Broad-Market ETF Forecast Validation",
        "",
        f"generated_at: `{_utc_now_iso()}`",
        f"forecast_file: `{forecast_path}`",
        f"symbols_expected: `{len(symbols)}`",
        f"symbols_with_forecast: `{len(forecast)}`",
        f"symbols_with_prices: `{len(prices)}`",
        "",
        "## Rank correlation sanity checks",
        "",
        f"- Spearman H1 vs realized trailing 1D: `{h1_vs_1d if h1_vs_1d is not None else 'n/a'}`",
        f"- Spearman H5 vs realized trailing 5D: `{h5_vs_5d if h5_vs_5d is not None else 'n/a'}`",
        f"- Spearman H5 vs realized trailing 20D: `{h5_vs_20d if h5_vs_20d is not None else 'n/a'}`",
        "",
        "> Note: this first report compares current forecast ranks against recent realized returns. It is a sanity check, not a true forward backtest. A true forward test requires saving forecast snapshots and revisiting them after H trading days.",
        "",
        "## Top forecast-ranked country ETFs",
        "",
        "| Symbol | H1 | H5 | Realized 1D | Realized 5D | Realized 20D |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for row in sorted_rows[: max(1, int(args.top))]:
        lines.append(
            "| {symbol} | {h1} | {h5} | {r1} | {r5} | {r20} |".format(
                symbol=row["symbol"],
                h1=_fmt_score(row.get("h1_score")),
                h5=_fmt_score(row.get("h5_score")),
                r1=_fmt_pct(row.get("realized_1d")),
                r5=_fmt_pct(row.get("realized_5d")),
                r20=_fmt_pct(row.get("realized_20d")),
            )
        )

    if missing_forecast:
        lines.extend(
            ["", "## Missing forecast symbols", "", ", ".join(missing_forecast)]
        )
    if missing_prices:
        lines.extend(["", "## Missing price symbols", "", ", ".join(missing_prices)])

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This report validates whether the new country ETF H1/H5 ranks are directionally sane against recent realized movement.",
            "- It does not prove news awareness.",
            "- It does not prove future accuracy.",
            "- Large disagreement is a signal to inspect model features, stale data timing, or local-market-vs-US-listed-ETF timing.",
            "",
        ]
    )

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"symbols_expected={len(symbols)}")
    print(f"symbols_with_forecast={len(forecast)}")
    print(f"symbols_with_prices={len(prices)}")
    print(f"missing_forecast={len(missing_forecast)}")
    print(f"missing_prices={len(missing_prices)}")
    print(f"h1_vs_realized_1d_spearman={h1_vs_1d}")
    print(f"h5_vs_realized_5d_spearman={h5_vs_5d}")
    print(f"h5_vs_realized_20d_spearman={h5_vs_20d}")
    print(f"csv={csv_path}")
    print(f"markdown={md_path}")

    return 0 if not missing_forecast else 1


if __name__ == "__main__":
    raise SystemExit(main())
