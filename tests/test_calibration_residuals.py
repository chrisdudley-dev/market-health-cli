from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.residuals import (
    RESIDUAL_SCHEMA_VERSION,
    build_residual_observation,
    forecast_score_for_horizon,
    residual_direction,
    summarize_residuals,
)
from market_health.calibration.schema import ReplayArtifactRow


def row(
    *,
    symbol: str = "SPY",
    replay_date: date = date(2026, 5, 20),
    current_score: float = 8.0,
    h1_score: float = 8.5,
    h5_score: float = 7.5,
) -> ReplayArtifactRow:
    return ReplayArtifactRow(
        replay_date=replay_date,
        symbol=symbol,
        current_score=current_score,
        h1_score=h1_score,
        h5_score=h5_score,
        blend_score=current_score,
        state="GREEN",
        audit_token=None,
    )


class CalibrationResidualsTest(unittest.TestCase):
    def test_residual_direction(self) -> None:
        self.assertEqual(residual_direction(0.25), "hot")
        self.assertEqual(residual_direction(-0.25), "cold")
        self.assertEqual(residual_direction(0.0), "neutral")

    def test_forecast_score_for_horizon(self) -> None:
        replay_row = row()

        self.assertEqual(forecast_score_for_horizon(replay_row, "H1"), 8.5)
        self.assertEqual(forecast_score_for_horizon(replay_row, "h5"), 7.5)

        with self.assertRaises(ValueError):
            forecast_score_for_horizon(replay_row, "H2")

    def test_build_residual_observation(self) -> None:
        observation = build_residual_observation(
            forecast_row=row(),
            target_date=date(2026, 5, 21),
            horizon="H1",
            realized_current_score=8.0,
            category="B",
            slot="B4",
            glyph="+",
            named_check="trend_confirmed",
        )

        self.assertEqual(observation.schema_version, RESIDUAL_SCHEMA_VERSION)
        self.assertEqual(observation.symbol, "SPY")
        self.assertEqual(observation.origin_date, "2026-05-20")
        self.assertEqual(observation.target_date, "2026-05-21")
        self.assertEqual(observation.horizon, "H1")
        self.assertEqual(observation.forecast_score, 8.5)
        self.assertEqual(observation.realized_current_score, 8.0)
        self.assertEqual(observation.residual, 0.5)
        self.assertEqual(observation.direction, "hot")
        self.assertEqual(observation.category, "B")
        self.assertEqual(observation.slot, "B4")
        self.assertEqual(observation.glyph, "+")
        self.assertEqual(observation.named_check, "trend_confirmed")

    def test_summarize_residuals_by_horizon(self) -> None:
        observations = [
            build_residual_observation(
                forecast_row=row(symbol="SPY", h1_score=8.5),
                target_date=date(2026, 5, 21),
                horizon="H1",
                realized_current_score=8.0,
            ),
            build_residual_observation(
                forecast_row=row(symbol="QQQ", h1_score=7.0),
                target_date=date(2026, 5, 21),
                horizon="H1",
                realized_current_score=7.5,
            ),
            build_residual_observation(
                forecast_row=row(symbol="SPY", h5_score=7.5),
                target_date=date(2026, 5, 25),
                horizon="H5",
                realized_current_score=7.5,
            ),
        ]

        summaries = summarize_residuals(observations, group_by=("horizon",))

        self.assertEqual(len(summaries), 2)
        h1 = next(item for item in summaries if item.group == {"horizon": "H1"})
        h5 = next(item for item in summaries if item.group == {"horizon": "H5"})

        self.assertEqual(h1.count, 2)
        self.assertEqual(h1.mean_residual, 0.0)
        self.assertEqual(h1.mean_abs_residual, 0.5)
        self.assertEqual(h1.hot_count, 1)
        self.assertEqual(h1.cold_count, 1)
        self.assertEqual(h1.neutral_count, 0)

        self.assertEqual(h5.count, 1)
        self.assertEqual(h5.neutral_count, 1)

    def test_summarize_residuals_by_category_slot_glyph(self) -> None:
        observations = [
            build_residual_observation(
                forecast_row=row(symbol="SPY", h1_score=8.5),
                target_date=date(2026, 5, 21),
                horizon="H1",
                realized_current_score=8.0,
                category="B",
                slot="B4",
                glyph="+",
            ),
            build_residual_observation(
                forecast_row=row(symbol="QQQ", h1_score=7.5),
                target_date=date(2026, 5, 21),
                horizon="H1",
                realized_current_score=7.0,
                category="B",
                slot="B4",
                glyph="+",
            ),
        ]

        summaries = summarize_residuals(
            observations,
            group_by=("category", "slot", "glyph", "horizon"),
        )

        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(
            summary.group,
            {"category": "B", "slot": "B4", "glyph": "+", "horizon": "H1"},
        )
        self.assertEqual(summary.count, 2)
        self.assertEqual(summary.mean_residual, 0.5)
        self.assertEqual(summary.hot_count, 2)


if __name__ == "__main__":
    unittest.main()
