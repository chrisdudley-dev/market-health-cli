from __future__ import annotations

from copy import deepcopy
from typing import Any

_FORECAST_INPUT_INVENTORY: list[dict[str, Any]] = [
    {
        "check": "A1",
        "label": "Catalyst Window",
        "dependency": "calendar/event provider",
        "current_handling": "proxy intentionally",
        "source_quality_when_missing": "proxy",
        "missing_behavior": "uses deterministic fallback calendar context",
    },
    {
        "check": "A2",
        "label": "Macro Calendar Pressure",
        "dependency": "VIX / volatility regime feed",
        "current_handling": "neutral intentionally",
        "source_quality_when_missing": "neutral",
        "missing_behavior": "neutral_check when VIX features are unavailable",
    },
    {
        "check": "A3",
        "label": "Earnings Cluster",
        "dependency": "earnings/calendar provider",
        "current_handling": "proxy intentionally",
        "source_quality_when_missing": "proxy",
        "missing_behavior": "uses deterministic fallback calendar context",
    },
    {
        "check": "A4",
        "label": "Policy / Regulation Risk",
        "dependency": "policy/calendar provider",
        "current_handling": "proxy intentionally",
        "source_quality_when_missing": "proxy",
        "missing_behavior": "uses deterministic fallback calendar context",
    },
    {
        "check": "A5",
        "label": "Headline Shock Proxy",
        "dependency": "news/headline feed",
        "current_handling": "proxy intentionally",
        "source_quality_when_missing": "proxy",
        "missing_behavior": "uses ATR, Bollinger width, and extension proxies",
    },
    {
        "check": "C4",
        "label": "Flow Pressure",
        "dependency": "flow.v1 provider cache",
        "current_handling": "proxy intentionally",
        "source_quality_when_missing": "proxy",
        "missing_behavior": "uses volume proxy when flow.v1 is missing or incomplete",
    },
    {
        "check": "D1",
        "label": "Volatility Trend",
        "dependency": "iv.v1 provider cache",
        "current_handling": "proxy intentionally",
        "source_quality_when_missing": "proxy",
        "missing_behavior": "uses ATR/Bollinger proxies when symbol IV is missing",
    },
    {
        "check": "E2",
        "label": "VIX Outlook",
        "dependency": "VIX / volatility regime feed",
        "current_handling": "neutral intentionally",
        "source_quality_when_missing": "neutral",
        "missing_behavior": "neutral_check when VIX features are unavailable",
    },
    {
        "check": "E5",
        "label": "Cross-Regime Pressure",
        "dependency": "defensive/cyclical universe regime context",
        "current_handling": "neutral intentionally",
        "source_quality_when_missing": "neutral",
        "missing_behavior": "neutral_check when defensive/cyclical coverage is insufficient",
    },
    {
        "check": "E6",
        "label": "Driver Alignment",
        "dependency": "VIX outlook and local RS context",
        "current_handling": "proxy intentionally",
        "source_quality_when_missing": "proxy",
        "missing_behavior": "uses E2 score and local RS proxy",
    },
]


def forecast_input_inventory() -> list[dict[str, Any]]:
    return deepcopy(_FORECAST_INPUT_INVENTORY)


def forecast_input_inventory_by_check() -> dict[str, dict[str, Any]]:
    return {str(row["check"]): row for row in forecast_input_inventory()}
