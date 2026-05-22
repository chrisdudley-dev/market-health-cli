from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from market_health.calibration.defaults import assert_not_live_runtime_path

CHECK_INVENTORY_SCHEMA_VERSION = "calibration_check_inventory.v1"

REPLAYABILITY_REPLAYABLE = "replayable"
REPLAYABILITY_EVENT_DEPENDENT = "event_dependent"
REPLAYABILITY_NEUTRAL_FALLBACK = "neutral_fallback"
REPLAYABILITY_EXCLUDED = "excluded"

REPLAYABILITY_CLASSES = (
    REPLAYABILITY_REPLAYABLE,
    REPLAYABILITY_EVENT_DEPENDENT,
    REPLAYABILITY_NEUTRAL_FALLBACK,
    REPLAYABILITY_EXCLUDED,
)

CHECK_INVENTORY_COLUMNS = (
    "schema_version",
    "category",
    "slot",
    "category_slot",
    "named_check",
    "function_name",
    "source_module",
    "replayability_class",
    "replay_source",
    "fallback_policy",
)


@dataclass(frozen=True)
class CheckInventoryRow:
    category: str
    slot: int
    named_check: str
    function_name: str
    source_module: str
    replayability_class: str
    replay_source: str
    fallback_policy: str
    schema_version: str = CHECK_INVENTORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        category = self.category.strip().upper()
        if category not in {"A", "B", "C", "D", "E"}:
            raise ValueError(f"unsupported check category: {self.category}")
        if not 1 <= self.slot <= 6:
            raise ValueError(f"unsupported check slot: {self.slot}")
        if self.replayability_class not in REPLAYABILITY_CLASSES:
            raise ValueError(
                f"unsupported replayability class: {self.replayability_class}"
            )
        if self.schema_version != CHECK_INVENTORY_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported check inventory schema version: {self.schema_version}"
            )

        object.__setattr__(self, "category", category)

    @property
    def category_slot(self) -> str:
        return f"{self.category}{self.slot}"

    def to_record(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "category": self.category,
            "slot": str(self.slot),
            "category_slot": self.category_slot,
            "named_check": self.named_check,
            "function_name": self.function_name,
            "source_module": self.source_module,
            "replayability_class": self.replayability_class,
            "replay_source": self.replay_source,
            "fallback_policy": self.fallback_policy,
        }


CHECK_INVENTORY: tuple[CheckInventoryRow, ...] = (
    CheckInventoryRow(
        "A",
        1,
        "Catalyst Window",
        "a1_catalyst_window",
        "market_health.forecast_checks_a_announcements",
        REPLAYABILITY_EVENT_DEPENDENT,
        "point-in-time catalyst calendar",
        "neutral when calendar feed is unavailable",
    ),
    CheckInventoryRow(
        "A",
        2,
        "Macro Calendar Pressure",
        "a2_macro_calendar_pressure",
        "market_health.forecast_checks_a_announcements",
        REPLAYABILITY_EVENT_DEPENDENT,
        "point-in-time macro calendar and VIX context",
        "neutral when required macro/VIX context is unavailable",
    ),
    CheckInventoryRow(
        "A",
        3,
        "Earnings Cluster",
        "a3_earnings_cluster",
        "market_health.forecast_checks_a_announcements",
        REPLAYABILITY_EVENT_DEPENDENT,
        "point-in-time earnings calendar",
        "neutral when earnings calendar is unavailable",
    ),
    CheckInventoryRow(
        "A",
        4,
        "Policy / Regulatory Risk",
        "a4_policy_reg_risk",
        "market_health.forecast_checks_a_announcements",
        REPLAYABILITY_EVENT_DEPENDENT,
        "point-in-time policy calendar",
        "neutral when policy calendar is unavailable",
    ),
    CheckInventoryRow(
        "A",
        5,
        "Headline Shock Proxy",
        "a5_headline_shock_proxy",
        "market_health.forecast_checks_a_announcements",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV-derived headline shock proxy",
        "neutral when reversal/return history is insufficient",
    ),
    CheckInventoryRow(
        "A",
        6,
        "Narrative Momentum",
        "a6_narrative_momentum",
        "market_health.forecast_checks_a_announcements",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV and relative-return history",
        "neutral when RS/return history is insufficient",
    ),
    CheckInventoryRow(
        "B",
        1,
        "Trend Persistence",
        "b1_trend_persistence",
        "market_health.forecast_checks_b_backdrop",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV trend history",
        "neutral when history is insufficient",
    ),
    CheckInventoryRow(
        "B",
        2,
        "Follow-Through Setup",
        "b2_follow_through_setup",
        "market_health.forecast_checks_b_backdrop",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV return history",
        "neutral when history is insufficient",
    ),
    CheckInventoryRow(
        "B",
        3,
        "RS Momentum vs SPY",
        "b3_rs_momentum",
        "market_health.forecast_checks_b_backdrop",
        REPLAYABILITY_REPLAYABLE,
        "relative-return history versus SPY",
        "neutral when RS history is insufficient",
    ),
    CheckInventoryRow(
        "B",
        4,
        "Support Cushion",
        "b4_support_cushion",
        "market_health.forecast_checks_b_backdrop",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV support-distance proxy",
        "neutral when history is insufficient",
    ),
    CheckInventoryRow(
        "B",
        5,
        "Participation Trend",
        "b5_participation_trend",
        "market_health.forecast_checks_b_backdrop",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV participation history",
        "neutral when participation history is insufficient",
    ),
    CheckInventoryRow(
        "B",
        6,
        "Acceleration vs Exhaustion",
        "b6_acceleration_vs_exhaustion",
        "market_health.forecast_checks_b_backdrop",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV acceleration/exhaustion history",
        "neutral when history is insufficient",
    ),
    CheckInventoryRow(
        "C",
        1,
        "Extension Risk",
        "c1_extension_risk",
        "market_health.forecast_checks_c_crowding",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV extension history",
        "neutral when history is insufficient",
    ),
    CheckInventoryRow(
        "C",
        2,
        "Volume Climax Risk",
        "c2_volume_climax_risk",
        "market_health.forecast_checks_c_crowding",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV volume history",
        "neutral when volume/history is insufficient",
    ),
    CheckInventoryRow(
        "C",
        3,
        "Breadth Thinning",
        "c3_breadth_thinning",
        "market_health.forecast_checks_c_crowding",
        REPLAYABILITY_REPLAYABLE,
        "universe return breadth history",
        "neutral when breadth window is insufficient",
    ),
    CheckInventoryRow(
        "C",
        4,
        "Flow Pressure",
        "c4_flow_pressure",
        "market_health.forecast_checks_c_crowding",
        REPLAYABILITY_NEUTRAL_FALLBACK,
        "flow metrics when available; OHLCV volume proxy otherwise",
        "records fallback proxy use when flow metrics are unavailable",
    ),
    CheckInventoryRow(
        "C",
        5,
        "Positioning Asymmetry",
        "c5_positioning_asymmetry",
        "market_health.forecast_checks_c_crowding",
        REPLAYABILITY_REPLAYABLE,
        "return-distribution history",
        "neutral when usable return window is insufficient",
    ),
    CheckInventoryRow(
        "C",
        6,
        "Correlation Crowding",
        "c6_correlation_crowding",
        "market_health.forecast_checks_c_crowding",
        REPLAYABILITY_REPLAYABLE,
        "correlation and dispersion history",
        "neutral when correlation inputs are insufficient",
    ),
    CheckInventoryRow(
        "D",
        1,
        "Volatility Trend",
        "d1_volatility_trend",
        "market_health.forecast_checks_d_danger",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV volatility history",
        "neutral when ATR/IV/Bollinger inputs are insufficient",
    ),
    CheckInventoryRow(
        "D",
        2,
        "Tail / Gap Risk",
        "d2_tail_gap_risk",
        "market_health.forecast_checks_d_danger",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV tail/gap history with optional catalyst context",
        "neutral when usable return window is insufficient",
    ),
    CheckInventoryRow(
        "D",
        3,
        "Market Coupling Trend",
        "d3_market_coupling_trend",
        "market_health.forecast_checks_d_danger",
        REPLAYABILITY_REPLAYABLE,
        "market correlation history",
        "neutral when market-coupling inputs are insufficient",
    ),
    CheckInventoryRow(
        "D",
        4,
        "Liquidity Stress",
        "d4_liquidity_stress",
        "market_health.forecast_checks_d_danger",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV liquidity and volume history",
        "neutral when liquidity inputs are insufficient",
    ),
    CheckInventoryRow(
        "D",
        5,
        "Drawdown Vulnerability",
        "d5_drawdown_vulnerability",
        "market_health.forecast_checks_d_danger",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV drawdown history",
        "neutral when drawdown inputs are insufficient",
    ),
    CheckInventoryRow(
        "D",
        6,
        "Risk / Reward Feasibility",
        "d6_risk_reward_feasibility",
        "market_health.forecast_checks_d_danger",
        REPLAYABILITY_REPLAYABLE,
        "OHLCV risk/reward proxy inputs",
        "neutral when feasibility inputs are insufficient",
    ),
    CheckInventoryRow(
        "E",
        1,
        "SPY Outlook",
        "e1_spy_outlook",
        "market_health.forecast_checks_e_environment",
        REPLAYABILITY_REPLAYABLE,
        "SPY trend and return history",
        "neutral when SPY inputs are insufficient",
    ),
    CheckInventoryRow(
        "E",
        2,
        "VIX Outlook",
        "e2_vix_outlook",
        "market_health.forecast_checks_e_environment",
        REPLAYABILITY_REPLAYABLE,
        "VIX history",
        "neutral when VIX inputs are insufficient",
    ),
    CheckInventoryRow(
        "E",
        3,
        "Leadership Persistence",
        "e3_leadership_persistence",
        "market_health.forecast_checks_e_environment",
        REPLAYABILITY_REPLAYABLE,
        "leadership return history",
        "neutral when leadership inputs are insufficient",
    ),
    CheckInventoryRow(
        "E",
        4,
        "Breadth Regime",
        "e4_breadth_regime",
        "market_health.forecast_checks_e_environment",
        REPLAYABILITY_REPLAYABLE,
        "universe breadth history",
        "neutral when breadth inputs are insufficient",
    ),
    CheckInventoryRow(
        "E",
        5,
        "Cross-Regime Pressure",
        "e5_cross_regime_pressure",
        "market_health.forecast_checks_e_environment",
        REPLAYABILITY_NEUTRAL_FALLBACK,
        "defensive/cyclical regime coverage",
        "separates measured neutral from insufficient-coverage fallback neutral",
    ),
    CheckInventoryRow(
        "E",
        6,
        "Driver Alignment",
        "e6_driver_alignment",
        "market_health.forecast_checks_e_environment",
        REPLAYABILITY_REPLAYABLE,
        "driver and leadership return history",
        "neutral when driver inputs are insufficient",
    ),
)


def iter_check_inventory() -> tuple[CheckInventoryRow, ...]:
    return tuple(sorted(CHECK_INVENTORY, key=lambda row: (row.category, row.slot)))


def check_inventory_records(
    rows: Iterable[CheckInventoryRow] | None = None,
) -> list[dict[str, str]]:
    selected_rows = iter_check_inventory() if rows is None else tuple(rows)
    return [row.to_record() for row in selected_rows]


def write_check_inventory_json(
    path: Path,
    rows: Iterable[CheckInventoryRow] | None = None,
) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": CHECK_INVENTORY_SCHEMA_VERSION,
        "rows": check_inventory_records(rows),
    }

    with NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    temp_path.replace(path)
    return path


def write_check_inventory_csv(
    path: Path,
    rows: Iterable[CheckInventoryRow] | None = None,
) -> Path:
    assert_not_live_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHECK_INVENTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(check_inventory_records(rows))

    return path
