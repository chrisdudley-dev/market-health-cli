#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

from market_health.stop_buy_levels import (
    generate_stop_buy_candidates,
    strongest_stop_buy_clusters,
)


def _utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _parse_symbols(value: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for raw in value.replace("\n", ",").split(","):
        sym = raw.strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)

    return out


def _atr14(df: pd.DataFrame) -> float | None:
    if not {"High", "Low", "Close"}.issubset(df.columns):
        return None

    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(14, min_periods=5).mean().dropna()
    if atr.empty:
        return None

    return float(atr.iloc[-1])


def _last_close(df: pd.DataFrame) -> float | None:
    if "Close" not in df.columns:
        return None

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        return None

    return float(close.iloc[-1])


def _recent_low_high(
    df: pd.DataFrame, lookback: int = 20
) -> tuple[float | None, float | None]:
    if not {"High", "Low"}.issubset(df.columns):
        return None, None

    low = pd.to_numeric(df["Low"], errors="coerce").dropna().tail(lookback)
    high = pd.to_numeric(df["High"], errors="coerce").dropna().tail(lookback)

    if low.empty or high.empty:
        return None, None

    return float(low.min()), float(high.max())


def select_executable_stop_buy_levels(
    candidates: list[dict[str, Any]],
    *,
    last_close: float,
    atr: float,
    recent_low: float,
    recent_high: float,
    buffer_atr: float = 0.25,
    min_cluster_size: int = 2,
) -> dict[str, Any]:
    fallback_stop = recent_low - (buffer_atr * atr)
    fallback_buy = recent_high + (buffer_atr * atr)

    stop = fallback_stop
    buy = fallback_buy
    stop_source = "recent_low_atr_fallback"
    buy_source = "recent_high_atr_fallback"

    clusters = strongest_stop_buy_clusters(
        candidates,
        current_price=last_close,
        atr=atr,
        min_cluster_size=min_cluster_size,
    )

    floor_cluster = clusters.get("floor")
    ceiling_cluster = clusters.get("ceiling")

    if floor_cluster is not None:
        stop = float(floor_cluster["lower"]) - (buffer_atr * atr)
        stop_source = "clustered_floor"

    if ceiling_cluster is not None:
        buy = float(ceiling_cluster["upper"]) + (buffer_atr * atr)
        buy_source = "clustered_ceiling"

    return {
        "stop": round(float(stop), 6),
        "buy": round(float(buy), 6),
        "stop_source": stop_source,
        "buy_source": buy_source,
        "fallback_stop": round(float(fallback_stop), 6),
        "fallback_buy": round(float(fallback_buy), 6),
        "floor_cluster": floor_cluster,
        "ceiling_cluster": ceiling_cluster,
    }


def _normalize_frame(data: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    frame = data

    if isinstance(data.columns, pd.MultiIndex):
        if symbol in data.columns.get_level_values(0):
            frame = data[symbol].copy()
        elif symbol in data.columns.get_level_values(-1):
            frame = data.xs(symbol, axis=1, level=-1).copy()
        else:
            return pd.DataFrame()

    rename = {str(c).title(): c for c in frame.columns}
    needed = {}
    for name in ("Open", "High", "Low", "Close", "Volume"):
        original = rename.get(name)
        if original is not None:
            needed[name] = frame[original]

    out = pd.DataFrame(needed).dropna(how="all")
    return out


def _download_symbol(symbol: str, *, period: str) -> pd.DataFrame:
    if yf is None:
        raise RuntimeError("yfinance is not available in this environment")

    data = yf.download(
        symbol,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    return _normalize_frame(data, symbol)


def compute_symbol_report(symbol: str, *, period: str) -> dict[str, Any]:
    df = _download_symbol(symbol, period=period)

    if df.empty:
        return {
            "symbol": symbol,
            "status": "missing_prices",
            "reason": "No OHLCV rows returned.",
        }

    last_close = _last_close(df)
    atr = _atr14(df)
    recent_low, recent_high = _recent_low_high(df)

    if last_close is None or atr is None or recent_low is None or recent_high is None:
        return {
            "symbol": symbol,
            "status": "insufficient_data",
            "reason": "Could not compute last close, ATR, recent low, or recent high.",
            "rows": int(len(df)),
        }

    candidates = generate_stop_buy_candidates(df)
    selected = select_executable_stop_buy_levels(
        candidates,
        last_close=last_close,
        atr=atr,
        recent_low=recent_low,
        recent_high=recent_high,
    )

    floor_cluster = selected.get("floor_cluster")
    ceiling_cluster = selected.get("ceiling_cluster")

    return {
        "symbol": symbol,
        "status": "ok",
        "rows": int(len(df)),
        "last_close": round(float(last_close), 6),
        "atr14": round(float(atr), 6),
        "recent_low_20d": round(float(recent_low), 6),
        "recent_high_20d": round(float(recent_high), 6),
        "stop": selected["stop"],
        "buy": selected["buy"],
        "stop_source": selected["stop_source"],
        "buy_source": selected["buy_source"],
        "fallback_stop": selected["fallback_stop"],
        "fallback_buy": selected["fallback_buy"],
        "candidate_count": len(candidates),
        "floor_center": None if floor_cluster is None else floor_cluster.get("center"),
        "floor_lower": None if floor_cluster is None else floor_cluster.get("lower"),
        "floor_upper": None if floor_cluster is None else floor_cluster.get("upper"),
        "floor_strength": None
        if floor_cluster is None
        else floor_cluster.get("strength"),
        "floor_sources": ""
        if floor_cluster is None
        else ",".join(floor_cluster.get("sources", [])),
        "ceiling_center": None
        if ceiling_cluster is None
        else ceiling_cluster.get("center"),
        "ceiling_lower": None
        if ceiling_cluster is None
        else ceiling_cluster.get("lower"),
        "ceiling_upper": None
        if ceiling_cluster is None
        else ceiling_cluster.get("upper"),
        "ceiling_strength": None
        if ceiling_cluster is None
        else ceiling_cluster.get("strength"),
        "ceiling_sources": ""
        if ceiling_cluster is None
        else ",".join(ceiling_cluster.get("sources", [])),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "symbol",
        "status",
        "rows",
        "last_close",
        "atr14",
        "recent_low_20d",
        "recent_high_20d",
        "stop",
        "buy",
        "stop_source",
        "buy_source",
        "fallback_stop",
        "fallback_buy",
        "candidate_count",
        "floor_center",
        "floor_lower",
        "floor_upper",
        "floor_strength",
        "floor_sources",
        "ceiling_center",
        "ceiling_lower",
        "ceiling_upper",
        "ceiling_strength",
        "ceiling_sources",
        "reason",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _write_markdown(path: Path, *, rows: list[dict[str, Any]], period: str) -> None:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    clustered_stops = sum(
        1 for row in ok_rows if row.get("stop_source") == "clustered_floor"
    )
    clustered_buys = sum(
        1 for row in ok_rows if row.get("buy_source") == "clustered_ceiling"
    )

    lines = [
        "# M42 Stop/Buy Math Validation Report",
        "",
        f"generated_at: `{_utc_now_iso()}`",
        f"period: `{period}`",
        f"symbols_checked: `{len(rows)}`",
        f"symbols_ok: `{len(ok_rows)}`",
        f"clustered_stop_count: `{clustered_stops}`",
        f"clustered_buy_count: `{clustered_buys}`",
        "",
        "## Contract",
        "",
        "- `Stop` is the actionable broker stop-loss trigger.",
        "- `Buy` is the actionable broker stop-buy trigger.",
        "- Dashboard output stays simple: no source columns are added.",
        "- ATR is used as a buffer/normalizer; clustered support/resistance supplies the floor/ceiling when available.",
        "",
        "## Current formula",
        "",
        "```text",
        "Stop = strongest_floor_cluster.lower - 0.25 * ATR14",
        "Buy  = strongest_ceiling_cluster.upper + 0.25 * ATR14",
        "Fallback Stop = recent_low_20d - 0.25 * ATR14",
        "Fallback Buy  = recent_high_20d + 0.25 * ATR14",
        "```",
        "",
        "## Symbol results",
        "",
        "| Symbol | Last | ATR14 | Stop | Stop Source | Buy | Buy Source | Floor Sources | Ceiling Sources |",
        "|---|---:|---:|---:|---|---:|---|---|---|",
    ]

    for row in rows:
        if row.get("status") != "ok":
            lines.append(
                f"| {row.get('symbol')} | - | - | - | {row.get('status')} | - | {row.get('reason', '-')} | - | - |"
            )
            continue

        lines.append(
            "| {symbol} | {last} | {atr} | {stop} | {stop_source} | {buy} | {buy_source} | {floor_sources} | {ceiling_sources} |".format(
                symbol=row.get("symbol"),
                last=_fmt(row.get("last_close")),
                atr=_fmt(row.get("atr14")),
                stop=_fmt(row.get("stop")),
                stop_source=row.get("stop_source"),
                buy=_fmt(row.get("buy")),
                buy_source=row.get("buy_source"),
                floor_sources=row.get("floor_sources") or "-",
                ceiling_sources=row.get("ceiling_sources") or "-",
            )
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "- `clustered_floor` means Stop came from a multi-candidate support/floor cluster.",
        "- `clustered_ceiling` means Buy came from a multi-candidate resistance/ceiling cluster.",
        "- `recent_low_atr_fallback` or `recent_high_atr_fallback` means not enough clustered evidence was available, so the old fallback was used.",
        "- This report is diagnostic only; it does not add terminal columns and does not place trades.",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        default="IBIT,SPMO,MTUM,VLUE,IWM,XLK,XLF,XLB,XLU,SGOV,CSWC",
        help="Comma-separated symbols to validate.",
    )
    parser.add_argument("--period", default="6mo")
    parser.add_argument(
        "--out-dir",
        default=str(Path.home() / ".cache" / "jerboa" / "reports"),
    )
    args = parser.parse_args()

    symbols = _parse_symbols(str(args.symbols))
    if not symbols:
        raise SystemExit("No symbols supplied")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        compute_symbol_report(symbol, period=str(args.period)) for symbol in symbols
    ]

    stamp = _utc_now_stamp()
    csv_path = out_dir / f"stop_buy_validation_{stamp}.csv"
    md_path = out_dir / f"stop_buy_validation_{stamp}.md"
    json_path = out_dir / f"stop_buy_validation_{stamp}.json"

    _write_csv(csv_path, rows)
    _write_markdown(md_path, rows=rows, period=str(args.period))
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")

    ok_rows = [row for row in rows if row.get("status") == "ok"]
    print(f"symbols_checked={len(rows)}")
    print(f"symbols_ok={len(ok_rows)}")
    print(
        "clustered_stop_count="
        f"{sum(1 for row in ok_rows if row.get('stop_source') == 'clustered_floor')}"
    )
    print(
        "clustered_buy_count="
        f"{sum(1 for row in ok_rows if row.get('buy_source') == 'clustered_ceiling')}"
    )
    print(f"csv={csv_path}")
    print(f"markdown={md_path}")
    print(f"json={json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
