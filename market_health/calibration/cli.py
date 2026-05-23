from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from market_health.calibration.authoritative_dataset_artifacts import (
    write_authoritative_dataset_artifacts,
)
from market_health.calibration.authoritative_dataset_builder import (
    build_authoritative_replay_dataset_rows,
)
from market_health.calibration.check_output import (
    CheckReplayRow,
    build_fixture_check_replay_rows,
)
from market_health.calibration.defaults import (
    assert_not_live_runtime_path,
    default_output_root,
)
from market_health.calibration.engine_metadata import capture_engine_metadata
from market_health.calibration.price_cache import read_historical_price_cache_csv
from market_health.calibration.range_failure_accounting import (
    run_range_replay_with_failure_accounting,
)
from market_health.calibration.range_progress import (
    range_progress_path,
    read_range_progress,
    write_range_progress,
)
from market_health.calibration.range_request import build_range_replay_request
from market_health.calibration.range_runner import RangeReplayResult, run_range_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="market-health-calibration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate replay scaffold defaults.")
    doctor.add_argument("--out", type=Path, default=default_output_root())

    range_replay = subparsers.add_parser(
        "range-replay",
        help="Run fixture-backed range replay over a historical price cache.",
    )
    range_replay.add_argument("--price-cache", type=Path, required=True)
    range_replay.add_argument("--start-date", type=_parse_date, required=True)
    range_replay.add_argument("--end-date", type=_parse_date, required=True)
    range_replay.add_argument("--symbols", nargs="+", required=True)
    range_replay.add_argument("--lookback-rows", type=int, default=20)
    range_replay.add_argument("--out", type=Path, default=default_output_root())
    range_replay.add_argument("--run-id", default="range-replay")
    range_replay.add_argument("--resume", action="store_true")
    range_replay.add_argument("--fail-fast", action="store_true")

    authoritative_dataset = subparsers.add_parser(
        "authoritative-dataset",
        help="Build the authoritative replay dataset from a historical price cache.",
    )
    authoritative_dataset.add_argument("--price-cache", type=Path, required=True)
    authoritative_dataset.add_argument("--start-date", type=_parse_date, required=True)
    authoritative_dataset.add_argument("--end-date", type=_parse_date, required=True)
    authoritative_dataset.add_argument("--symbols", nargs="+", required=True)
    authoritative_dataset.add_argument("--lookback-rows", type=int, default=20)
    authoritative_dataset.add_argument(
        "--out", type=Path, default=default_output_root()
    )
    authoritative_dataset.add_argument(
        "--dataset-run-id",
        default="authoritative-replay-dataset",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "doctor":
        output_root = args.out.expanduser()
        assert_not_live_runtime_path(output_root)
        payload = {
            "status": "ok",
            "output_root": str(output_root),
            "engine": capture_engine_metadata(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "range-replay":
        payload = _run_range_replay_command(args)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "authoritative-dataset":
        payload = _run_authoritative_dataset_command(args)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


def _run_range_replay_command(args: argparse.Namespace) -> dict[str, object]:
    output_root = args.out.expanduser()
    assert_not_live_runtime_path(output_root)

    price_cache_path = args.price_cache.expanduser()
    price_cache = read_historical_price_cache_csv(
        price_cache_path,
        symbols=args.symbols,
    )
    request = build_range_replay_request(
        start_date=args.start_date,
        end_date=args.end_date,
        symbols=args.symbols,
        lookback_rows=args.lookback_rows,
        output_root=output_root,
    )

    progress = None
    progress_path = range_progress_path(output_root)
    if args.resume and progress_path.exists():
        progress = read_range_progress(output_root)

    result = run_range_replay_with_failure_accounting(
        request=request,
        price_rows=price_cache.rows,
        run_id=args.run_id,
        progress=progress,
        fail_fast=args.fail_fast,
    )
    written_progress_path = write_range_progress(output_root, result.progress)

    return {
        "status": "ok" if result.failed_date_count == 0 else "completed_with_failures",
        "command": "range-replay",
        "price_cache_path": str(price_cache_path),
        "progress_path": str(written_progress_path),
        "result": result.to_record(),
    }


def _run_authoritative_dataset_command(args: argparse.Namespace) -> dict[str, object]:
    output_root = args.out.expanduser()
    assert_not_live_runtime_path(output_root)

    price_cache_path = args.price_cache.expanduser()
    price_cache = read_historical_price_cache_csv(
        price_cache_path,
        symbols=args.symbols,
    )
    range_request = build_range_replay_request(
        start_date=args.start_date,
        end_date=args.end_date,
        symbols=args.symbols,
        lookback_rows=args.lookback_rows,
        output_root=output_root,
    )
    range_result = run_range_replay(
        request=range_request,
        price_rows=price_cache.rows,
    )
    check_rows = _build_authoritative_dataset_check_rows(range_result)
    dataset_rows = build_authoritative_replay_dataset_rows(
        range_result=range_result,
        check_rows=check_rows,
        price_rows=price_cache.rows,
        dataset_run_id=args.dataset_run_id,
    )
    artifacts = write_authoritative_dataset_artifacts(
        output_root=output_root,
        rows=dataset_rows,
        dataset_run_id=args.dataset_run_id,
    )

    return {
        "status": "ok",
        "command": "authoritative-dataset",
        "price_cache_path": str(price_cache_path),
        "dataset_run_id": args.dataset_run_id,
        "row_count": artifacts.row_count,
        "artifacts": artifacts.to_record(),
    }


def _build_authoritative_dataset_check_rows(
    range_result: RangeReplayResult,
) -> tuple[CheckReplayRow, ...]:
    rows: list[CheckReplayRow] = []
    for result in range_result.results:
        eligible_symbols = result.asof_input_record.get("eligible_symbols")
        if isinstance(eligible_symbols, list | tuple):
            symbols = tuple(str(symbol) for symbol in eligible_symbols)
        else:
            symbols = tuple(row.symbol for row in result.rows)

        rows.extend(
            build_fixture_check_replay_rows(
                replay_date=result.replay_date,
                symbols=symbols,
            )
        )

    return tuple(rows)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected YYYY-MM-DD date, got: {value}"
        ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
