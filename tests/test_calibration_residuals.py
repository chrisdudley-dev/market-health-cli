from __future__ import annotations

import unittest
from datetime import date

from market_health.calibration.authoritative_dataset import (
    REALIZED_OUTCOME_AVAILABLE,
    REALIZED_OUTCOME_MISSING,
    REALIZED_OUTCOME_NOT_APPLICABLE,
    AuthoritativeReplayDatasetRow,
)
from market_health.calibration.residuals import (
    RESIDUAL_ATTRIBUTION_COLUMNS,
    RESIDUAL_ATTRIBUTION_SCHEMA_VERSION,
    RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS,
    RESIDUAL_ATTRIBUTION_SUMMARY_SCHEMA_VERSION,
    RESIDUAL_SCHEMA_VERSION,
    ResidualAttributionRow,
    ResidualAttributionSummaryRow,
    build_residual_attribution_rows,
    build_residual_observation,
    summarize_residual_attribution_rows,
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


class ResidualAttributionRowTest(unittest.TestCase):
    def test_record_has_stable_shape(self) -> None:
        residual_row = residual_attribution_row()

        record = residual_row.to_record()

        self.assertEqual(tuple(record.keys()), RESIDUAL_ATTRIBUTION_COLUMNS)
        self.assertEqual(record["schema_version"], RESIDUAL_ATTRIBUTION_SCHEMA_VERSION)
        self.assertEqual(record["replay_date"], "2026-05-20")
        self.assertEqual(record["symbol"], "SPY")
        self.assertEqual(record["horizon"], "H1")
        self.assertEqual(record["target_date"], "2026-05-21")
        self.assertEqual(record["forecast_score"], 8.5)
        self.assertEqual(record["realized_current_score"], 8.0)
        self.assertEqual(record["residual"], 0.5)
        self.assertEqual(record["residual_direction"], "hot")
        self.assertEqual(record["category_slot"], "B4")
        self.assertEqual(record["dataset_run_id"], "dataset-test")
        self.assertEqual(record["residual_attribution_run_id"], "m52-test")

    def test_normalizes_symbol_horizon_and_category(self) -> None:
        residual_row = residual_attribution_row(
            symbol=" spy ",
            horizon=" h5 ",
            category=" b ",
            slot=5,
            forecast_score=7.0,
            realized_current_score=7.5,
            residual=-0.5,
            residual_direction="cold",
        )

        self.assertEqual(residual_row.symbol, "SPY")
        self.assertEqual(residual_row.horizon, "H5")
        self.assertEqual(residual_row.category, "B")
        self.assertEqual(residual_row.category_slot, "B5")

    def test_rejects_invalid_horizon(self) -> None:
        with self.assertRaisesRegex(ValueError, "horizon"):
            residual_attribution_row(horizon="C")

    def test_rejects_direction_that_does_not_match_residual_sign(self) -> None:
        with self.assertRaisesRegex(ValueError, "direction"):
            residual_attribution_row(
                residual=0.5,
                residual_direction="cold",
            )

    def test_rejects_residual_that_does_not_match_scores(self) -> None:
        with self.assertRaisesRegex(ValueError, "forecast_score minus"):
            residual_attribution_row(
                forecast_score=8.5,
                realized_current_score=8.0,
                residual=0.25,
                residual_direction="hot",
            )

    def test_rejects_invalid_schema_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema version"):
            residual_attribution_row(schema_version="bad.version")


def residual_attribution_row(
    *,
    symbol: str = "SPY",
    horizon: str = "H1",
    category: str = "B",
    slot: int = 4,
    forecast_score: float = 8.5,
    realized_current_score: float = 8.0,
    residual: float = 0.5,
    residual_direction: str = "hot",
    schema_version: str = RESIDUAL_ATTRIBUTION_SCHEMA_VERSION,
    glyph: str = "+",
    named_check: str = "trend_confirmed",
    replayability_class: str = "replayable",
    measurement_status: str = "measured",
    residual_attribution_run_id: str = "m52-test",
) -> ResidualAttributionRow:
    return ResidualAttributionRow(
        replay_date=date(2026, 5, 20),
        symbol=symbol,
        horizon=horizon,
        target_date=date(2026, 5, 21),
        forecast_score=forecast_score,
        realized_current_score=realized_current_score,
        residual=residual,
        residual_direction=residual_direction,
        realized_return=0.03,
        category=category,
        slot=slot,
        glyph=glyph,
        named_check=named_check,
        check_score=4.1,
        replayability_class=replayability_class,
        measurement_status=measurement_status,
        source_module="fixture.module",
        function_name="check_b4",
        audit_token="single-date-asof:2026-05-20:SPY:1:100.0000",
        dataset_run_id="dataset-test",
        residual_attribution_run_id=residual_attribution_run_id,
        schema_version=schema_version,
    )


class ResidualAttributionBuilderTest(unittest.TestCase):
    def test_builds_rows_from_available_authoritative_rows(self) -> None:
        rows = build_residual_attribution_rows(
            [
                authoritative_dataset_row(
                    horizon="H1",
                    h1_score=8.5,
                    realized_current_score=8.0,
                    realized_return=0.03,
                )
            ],
            residual_attribution_run_id="m52-builder-test",
        )

        self.assertEqual(len(rows), 1)
        residual_row = rows[0]
        self.assertEqual(residual_row.symbol, "SPY")
        self.assertEqual(residual_row.horizon, "H1")
        self.assertEqual(residual_row.forecast_score, 8.5)
        self.assertEqual(residual_row.realized_current_score, 8.0)
        self.assertEqual(residual_row.residual, 0.5)
        self.assertEqual(residual_row.residual_direction, "hot")
        self.assertEqual(residual_row.realized_return, 0.03)
        self.assertEqual(residual_row.category_slot, "B4")
        self.assertEqual(residual_row.dataset_run_id, "dataset-test")
        self.assertEqual(residual_row.residual_attribution_run_id, "m52-builder-test")

    def test_uses_h5_score_for_h5_rows(self) -> None:
        rows = build_residual_attribution_rows(
            [
                authoritative_dataset_row(
                    horizon="H5",
                    h5_score=6.5,
                    realized_current_score=7.0,
                    realized_return=0.05,
                )
            ]
        )

        self.assertEqual(rows[0].forecast_score, 6.5)
        self.assertEqual(rows[0].residual, -0.5)
        self.assertEqual(rows[0].residual_direction, "cold")

    def test_excludes_missing_and_not_applicable_outcomes(self) -> None:
        rows = build_residual_attribution_rows(
            [
                authoritative_dataset_row(
                    horizon="H1",
                    realized_outcome_status=REALIZED_OUTCOME_MISSING,
                    target_date=date(2026, 5, 21),
                    realized_current_score=None,
                    realized_return=None,
                ),
                authoritative_dataset_row(
                    horizon="C",
                    realized_outcome_status=REALIZED_OUTCOME_NOT_APPLICABLE,
                    target_date=None,
                    realized_current_score=None,
                    realized_return=None,
                ),
                authoritative_dataset_row(
                    horizon="H5",
                    realized_outcome_status=REALIZED_OUTCOME_AVAILABLE,
                    target_date=date(2026, 5, 27),
                    h5_score=7.5,
                    realized_current_score=7.5,
                    realized_return=0.01,
                ),
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].horizon, "H5")
        self.assertEqual(rows[0].residual_direction, "neutral")

    def test_rows_are_sorted_deterministically(self) -> None:
        rows = build_residual_attribution_rows(
            [
                authoritative_dataset_row(
                    symbol="QQQ",
                    category="C",
                    slot=2,
                    horizon="H1",
                ),
                authoritative_dataset_row(
                    symbol="SPY",
                    category="B",
                    slot=4,
                    horizon="H5",
                    target_date=date(2026, 5, 27),
                ),
                authoritative_dataset_row(
                    symbol="SPY",
                    category="A",
                    slot=1,
                    horizon="H1",
                ),
            ]
        )

        self.assertEqual(
            [(row.symbol, row.category, row.slot, row.horizon) for row in rows],
            [
                ("QQQ", "C", 2, "H1"),
                ("SPY", "A", 1, "H1"),
                ("SPY", "B", 4, "H5"),
            ],
        )


def authoritative_dataset_row(
    *,
    replay_date: date = date(2026, 5, 20),
    symbol: str = "SPY",
    current_score: float = 8.0,
    h1_score: float = 8.5,
    h5_score: float = 7.5,
    blend_score: float = 8.0,
    state: str = "GREEN",
    horizon: str = "H1",
    target_date: date | None = date(2026, 5, 21),
    realized_current_score: float | None = 8.0,
    realized_return: float | None = 0.03,
    realized_outcome_status: str = REALIZED_OUTCOME_AVAILABLE,
    category: str = "B",
    slot: int = 4,
    glyph: str = "+",
    named_check: str = "trend_confirmed",
    replayability_class: str = "replayable",
    measurement_status: str = "measured",
) -> AuthoritativeReplayDatasetRow:
    return AuthoritativeReplayDatasetRow(
        replay_date=replay_date,
        symbol=symbol,
        current_score=current_score,
        h1_score=h1_score,
        h5_score=h5_score,
        blend_score=blend_score,
        state=state,
        horizon=horizon,
        target_date=target_date,
        realized_current_score=realized_current_score,
        realized_return=realized_return,
        realized_outcome_status=realized_outcome_status,
        category=category,
        slot=slot,
        glyph=glyph,
        named_check=named_check,
        check_score=4.1,
        replayability_class=replayability_class,
        measurement_status=measurement_status,
        source_module="fixture.module",
        function_name="check_b4",
        audit_token="single-date-asof:2026-05-20:SPY:1:100.0000",
        dataset_run_id="dataset-test",
    )


class ResidualAttributionSummaryRowTest(unittest.TestCase):
    def test_record_has_stable_shape(self) -> None:
        summary = ResidualAttributionSummaryRow(
            group_name="horizon+category_slot",
            group_value="H1|B4",
            horizon="H1",
            category_slot="B4",
            observation_count=2,
            mean_residual=0.125,
            mean_abs_residual=0.375,
            hot_count=1,
            cold_count=1,
            neutral_count=0,
            residual_attribution_run_id="m52-test",
        )

        record = summary.to_record()

        self.assertEqual(tuple(record.keys()), RESIDUAL_ATTRIBUTION_SUMMARY_COLUMNS)
        self.assertEqual(
            record["schema_version"],
            RESIDUAL_ATTRIBUTION_SUMMARY_SCHEMA_VERSION,
        )
        self.assertEqual(record["group_name"], "horizon+category_slot")
        self.assertEqual(record["group_value"], "H1|B4")
        self.assertEqual(record["observation_count"], 2)
        self.assertEqual(record["mean_residual"], 0.125)
        self.assertEqual(record["mean_abs_residual"], 0.375)

    def test_rejects_direction_count_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "direction counts"):
            ResidualAttributionSummaryRow(
                group_name="horizon",
                group_value="H1",
                horizon="H1",
                observation_count=2,
                mean_residual=0.0,
                mean_abs_residual=0.5,
                hot_count=1,
                cold_count=0,
                neutral_count=0,
                residual_attribution_run_id="m52-test",
            )

    def test_rejects_invalid_schema_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema version"):
            ResidualAttributionSummaryRow(
                group_name="horizon",
                group_value="H1",
                horizon="H1",
                observation_count=1,
                mean_residual=0.0,
                mean_abs_residual=0.0,
                hot_count=0,
                cold_count=0,
                neutral_count=1,
                residual_attribution_run_id="m52-test",
                schema_version="bad.version",
            )


class ResidualAttributionSummaryBuilderTest(unittest.TestCase):
    def test_summarizes_by_horizon(self) -> None:
        rows = [
            residual_attribution_row(
                symbol="SPY",
                horizon="H1",
                forecast_score=8.5,
                realized_current_score=8.0,
                residual=0.5,
                residual_direction="hot",
            ),
            residual_attribution_row(
                symbol="QQQ",
                horizon="H1",
                forecast_score=7.25,
                realized_current_score=7.5,
                residual=-0.25,
                residual_direction="cold",
            ),
            residual_attribution_row(
                symbol="IWM",
                horizon="H5",
                forecast_score=6.0,
                realized_current_score=6.0,
                residual=0.0,
                residual_direction="neutral",
            ),
        ]

        summaries = summarize_residual_attribution_rows(
            rows,
            groupings=(("horizon",),),
        )

        self.assertEqual(len(summaries), 2)
        h1 = next(item for item in summaries if item.group_value == "H1")
        h5 = next(item for item in summaries if item.group_value == "H5")

        self.assertEqual(h1.group_name, "horizon")
        self.assertEqual(h1.horizon, "H1")
        self.assertEqual(h1.observation_count, 2)
        self.assertEqual(h1.mean_residual, 0.125)
        self.assertEqual(h1.mean_abs_residual, 0.375)
        self.assertEqual(h1.hot_count, 1)
        self.assertEqual(h1.cold_count, 1)
        self.assertEqual(h1.neutral_count, 0)

        self.assertEqual(h5.observation_count, 1)
        self.assertEqual(h5.neutral_count, 1)

    def test_summarizes_by_category_slot_glyph_and_named_check(self) -> None:
        rows = [
            residual_attribution_row(
                symbol="SPY",
                category="B",
                slot=4,
                glyph="+",
                named_check="trend_confirmed",
            ),
            residual_attribution_row(
                symbol="QQQ",
                category="B",
                slot=4,
                glyph="+",
                named_check="trend_confirmed",
            ),
            residual_attribution_row(
                symbol="IWM",
                category="C",
                slot=2,
                glyph="-",
                named_check="pressure_warning",
                forecast_score=7.0,
                realized_current_score=7.5,
                residual=-0.5,
                residual_direction="cold",
            ),
        ]

        summaries = summarize_residual_attribution_rows(
            rows,
            groupings=(
                ("horizon", "category_slot", "glyph"),
                ("horizon", "named_check"),
            ),
        )

        category_slot = next(
            item for item in summaries if item.group_value == "H1|B4|+"
        )
        named_check = next(
            item for item in summaries if item.group_value == "H1|trend_confirmed"
        )

        self.assertEqual(category_slot.group_name, "horizon+category_slot+glyph")
        self.assertEqual(category_slot.horizon, "H1")
        self.assertEqual(category_slot.category_slot, "B4")
        self.assertEqual(category_slot.glyph, "+")
        self.assertEqual(category_slot.observation_count, 2)

        self.assertEqual(named_check.group_name, "horizon+named_check")
        self.assertEqual(named_check.named_check, "trend_confirmed")
        self.assertEqual(named_check.observation_count, 2)

    def test_summarizes_replayability_and_measurement_status(self) -> None:
        rows = [
            residual_attribution_row(
                replayability_class="replayable",
                measurement_status="measured",
            ),
            residual_attribution_row(
                symbol="QQQ",
                replayability_class="replayable",
                measurement_status="fallback_neutral",
                forecast_score=7.0,
                realized_current_score=7.5,
                residual=-0.5,
                residual_direction="cold",
            ),
        ]

        summaries = summarize_residual_attribution_rows(
            rows,
            groupings=(
                ("horizon", "replayability_class"),
                ("horizon", "measurement_status"),
            ),
        )

        replayable = next(
            item for item in summaries if item.group_value == "H1|replayable"
        )
        fallback_neutral = next(
            item for item in summaries if item.group_value == "H1|fallback_neutral"
        )

        self.assertEqual(replayable.replayability_class, "replayable")
        self.assertEqual(replayable.observation_count, 2)
        self.assertEqual(fallback_neutral.measurement_status, "fallback_neutral")
        self.assertEqual(fallback_neutral.observation_count, 1)

    def test_summary_rows_are_sorted_deterministically(self) -> None:
        rows = [
            residual_attribution_row(symbol="SPY", horizon="H5"),
            residual_attribution_row(symbol="QQQ", horizon="H1"),
        ]

        summaries = summarize_residual_attribution_rows(
            rows,
            groupings=(("horizon",),),
        )

        self.assertEqual([item.group_value for item in summaries], ["H1", "H5"])


if __name__ == "__main__":
    unittest.main()
