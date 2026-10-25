"""Normalize explicit input bars and Yahoo chart responses for the shared engine."""

import pandas as pd


FIELDS = ("Open", "High", "Low", "Close", "Volume")


def frames_from_document(document):
    frames = {}
    for symbol, block in document.get("series", {}).items():
        try:
            frame = pd.DataFrame(
                {k: block[k] for k in FIELDS}, index=pd.to_datetime(block["dates"])
            )
            if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
                raise ValueError("Bars must have increasing unique dates.")
            frames[symbol] = frame
        except (KeyError, TypeError, ValueError):
            frames[symbol] = pd.DataFrame()
    return frames


def frames_from_charts(document):
    """Match unadjusted daily OHLCV inputs: no rescaling, backfill or price repair."""
    frames = {}
    errors = dict(document.get("errors", {}))
    for symbol, response in document.get("charts", {}).items():
        try:
            chart = response["chart"]
            if chart.get("error") or not chart.get("result"):
                raise ValueError("Data source did not return a chart.")
            result = chart["result"][0]
            quotes = result["indicators"]["quote"][0]
            zone = result["meta"].get("exchangeTimezoneName", "America/New_York")
            dates = (
                pd.to_datetime(result["timestamp"], unit="s", utc=True)
                .tz_convert(zone)
                .normalize()
                .tz_localize(None)
            )
            frames[symbol] = pd.DataFrame(
                {k: quotes[k.lower()] for k in FIELDS}, index=dates
            ).dropna(how="all")
            # Match engine.safe_download: Yahoo includes fully empty holiday rows,
            # especially for VIX. Keep partial rows so validation still fails closed.
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            frames[symbol] = pd.DataFrame()
            errors[symbol] = str(exc)
    return frames, errors
