from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from market_health.calibration.authoritative_dataset import (
    AuthoritativeReplayDatasetRow,
)
from market_health.calibration.check_output import CheckReplayRow
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.range_runner import RangeReplayResult
from market_health.calibration.realized_outcomes import (
    RealizedForwardOutcome,
    resolve_realized_forward_outcome,
)
from market_health.calibration.schema import ReplayArtifactRow
from market_health.calibration.single_date_replay import SingleDateReplayResult

AUTHORITATIVE_DATASET_BUILD_SCHEMA_VERSION = (
    "calibration_authoritative_dataset_build.v1"
)


@dataclass(frozen=True)
class ReplayRowContext:
    single_date_result: SingleDateReplayResult
    replay_row: ReplayArtifactRow


def build_authoritative_replay_dataset_rows(
    *,
    range_result: RangeReplayResult,
    check_rows: Iterable[CheckReplayRow],
    price_rows: Iterable[HistoricalPriceRow],
    dataset_run_id: str = "authoritative-replay-dataset",
) -> tuple[AuthoritativeReplayDatasetRow, ...]:
    replay_lookup = _build_replay_lookup(range_result)
    source_price_rows = tuple(price_rows)
    outcome_lookup: dict[tuple[date, str, str], RealizedForwardOutcome] = {}

    dataset_rows: list[AuthoritativeReplayDatasetRow] = []
    for check_row in sorted(check_rows, key=_check_row_key):
        replay_context = _require_replay_context(replay_lookup, check_row)
        outcome_key = (
            check_row.replay_date,
            check_row.symbol,
            check_row.horizon,
        )
        outcome = outcome_lookup.get(outcome_key)
        if outcome is None:
            outcome = resolve_realized_forward_outcome(
                source_price_rows,
                replay_date=check_row.replay_date,
                symbol=check_row.symbol,
                horizon=check_row.horizon,
            )
            outcome_lookup[outcome_key] = outcome

        dataset_rows.append(
            _build_dataset_row(
                replay_context=replay_context,
                check_row=check_row,
                outcome=outcome,
                range_result=range_result,
                dataset_run_id=dataset_run_id,
            )
        )

    return tuple(sorted(dataset_rows, key=_dataset_row_key))


def _build_dataset_row(
    *,
    replay_context: ReplayRowContext,
    check_row: CheckReplayRow,
    outcome: RealizedForwardOutcome,
    range_result: RangeReplayResult,
    dataset_run_id: str,
) -> AuthoritativeReplayDatasetRow:
    replay_row = replay_context.replay_row

    return AuthoritativeReplayDatasetRow(
        replay_date=check_row.replay_date,
        symbol=check_row.symbol,
        current_score=replay_row.current_score,
        h1_score=replay_row.h1_score,
        h5_score=replay_row.h5_score,
        blend_score=replay_row.blend_score,
        state=replay_row.state,
        horizon=check_row.horizon,
        target_date=outcome.target_date,
        realized_current_score=outcome.realized_current_score,
        realized_return=outcome.realized_return,
        realized_outcome_status=outcome.realized_outcome_status,
        category=check_row.category,
        slot=check_row.slot,
        glyph=check_row.glyph,
        named_check=check_row.named_check,
        check_score=check_row.score,
        replayability_class=check_row.replayability_class,
        measurement_status=check_row.measurement_status,
        source_module=check_row.source_module,
        function_name=check_row.function_name,
        replay_row_schema_version=str(replay_row.to_record()["schema_version"]),
        check_row_schema_version=check_row.schema_version,
        single_date_replay_schema_version=replay_context.single_date_result.schema_version,
        range_replay_schema_version=range_result.schema_version,
        audit_token=replay_row.audit_token,
        dataset_run_id=dataset_run_id,
    )


def _build_replay_lookup(
    range_result: RangeReplayResult,
) -> dict[tuple[date, str], ReplayRowContext]:
    lookup: dict[tuple[date, str], ReplayRowContext] = {}
    for single_date_result in range_result.results:
        for replay_row in single_date_result.rows:
            key = (single_date_result.replay_date, replay_row.symbol)
            if key in lookup:
                raise ValueError(
                    "duplicate replay row for authoritative dataset key: "
                    f"{key[0].isoformat()} {key[1]}"
                )
            lookup[key] = ReplayRowContext(
                single_date_result=single_date_result,
                replay_row=replay_row,
            )
    return lookup


def _require_replay_context(
    replay_lookup: dict[tuple[date, str], ReplayRowContext],
    check_row: CheckReplayRow,
) -> ReplayRowContext:
    key = (check_row.replay_date, check_row.symbol)
    try:
        return replay_lookup[key]
    except KeyError as exc:
        raise KeyError(
            "check replay row has no matching replay row: "
            f"{check_row.replay_date.isoformat()} {check_row.symbol}"
        ) from exc


def _check_row_key(row: CheckReplayRow) -> tuple[date, str, str, int, str]:
    return (row.replay_date, row.symbol, row.category, row.slot, row.horizon)


def _dataset_row_key(
    row: AuthoritativeReplayDatasetRow,
) -> tuple[date, str, str, int, str]:
    return (row.replay_date, row.symbol, row.category, row.slot, row.horizon)
