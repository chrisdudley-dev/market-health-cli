from __future__ import annotations

import argparse
import shlex
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, List, Mapping, Optional, Sequence

from market_health.alert_cooldowns import (
    apply_alert_cooldowns,
    read_alert_history_from_store,
)
from market_health.alert_detectors import (
    AlertCandidate,
    detect_forecast_warnings,
    detect_position_inventory_changes,
    detect_position_state_changes,
)
from market_health.alert_snapshots import (
    HeldPositionSnapshot,
    collect_held_position_snapshots,
    load_ui_doc,
    write_held_position_snapshots,
)
from market_health.alert_store import (
    add_system_event,
    apply_migrations,
    connect,
    finish_run,
    start_run,
)
from market_health.telegram_notifier import (
    Sender,
    TelegramConfig,
    load_telegram_config,
    send_and_record_alert_candidate,
)

DEFAULT_REFRESH_CMD = ("scripts/jerboa/bin/jerboa-market-health-refresh-all",)


@dataclass(frozen=True)
class AlertRunnerConfig:
    db_path: Path
    ui_path: Path
    telegram_config_path: Optional[Path] = None
    telegram_mode: Optional[str] = None
    no_refresh: bool = False
    refresh_cmd: Sequence[str] = DEFAULT_REFRESH_CMD
    trigger_name: str = "manual"
    git_commit: Optional[str] = None
    current_drop_threshold: float = 5.0
    previous_drop_threshold: float = 7.0
    healthy_score_floor: float = 55.0


@dataclass(frozen=True)
class AlertRunResult:
    exit_code: int
    run_id: int
    status: str
    snapshots_written: int = 0
    candidates_count: int = 0
    allowed_count: int = 0
    suppressed_count: int = 0
    error_text: Optional[str] = None


RefreshFn = Callable[[], int]


def _read_previous_snapshots(
    *,
    db_path: Path,
    before_run_id: int,
) -> dict[str, Mapping[str, object]]:
    with connect(db_path) as conn:
        apply_migrations(conn)
        row = conn.execute(
            """
            SELECT MAX(run_id) AS run_id
            FROM symbol_snapshots
            WHERE run_id < ?
            """,
            (int(before_run_id),),
        ).fetchone()

        previous_run_id = row["run_id"] if row else None
        if previous_run_id is None:
            return {}

        rows = conn.execute(
            """
            SELECT symbol, state, current_score, h1_score, h5_score
            FROM symbol_snapshots
            WHERE run_id = ? AND is_held = 1
            ORDER BY symbol
            """,
            (int(previous_run_id),),
        ).fetchall()

    return {str(row["symbol"]): dict(row) for row in rows}


def _snapshot_states(
    snapshots: Sequence[HeldPositionSnapshot],
) -> dict[str, Optional[str]]:
    return {snapshot.symbol: snapshot.state for snapshot in snapshots}


def _run_refresh(config: AlertRunnerConfig, refresh_fn: Optional[RefreshFn]) -> int:
    if config.no_refresh:
        return 0

    if refresh_fn is not None:
        return int(refresh_fn())

    return subprocess.run(
        list(config.refresh_cmd),
        check=False,
        text=True,
        capture_output=True,
    ).returncode


def _load_telegram_config(config: AlertRunnerConfig) -> TelegramConfig:
    if config.telegram_config_path is None:
        telegram = TelegramConfig(mode="disabled")
    else:
        telegram = load_telegram_config(config.telegram_config_path)

    if config.telegram_mode is not None:
        telegram = replace(telegram, mode=config.telegram_mode)

    return telegram


def _detect_alerts(
    *,
    previous: Mapping[str, Mapping[str, object]],
    current_snapshots: Sequence[HeldPositionSnapshot],
    current_drop_threshold: float,
    previous_drop_threshold: float,
    healthy_score_floor: float,
) -> List[AlertCandidate]:
    current_symbols = [snapshot.symbol for snapshot in current_snapshots]

    candidates: List[AlertCandidate] = []
    candidates.extend(
        detect_position_inventory_changes(
            previous_symbols=previous.keys(),
            current_symbols=current_symbols,
        )
    )
    candidates.extend(
        detect_position_state_changes(
            previous_states={
                symbol: row.get("state") for symbol, row in previous.items()
            },
            current_states=_snapshot_states(current_snapshots),
        )
    )

    for snapshot in current_snapshots:
        prev = previous.get(snapshot.symbol, {})
        candidates.extend(
            detect_forecast_warnings(
                symbol=snapshot.symbol,
                current_score=snapshot.current_score,
                h1_score=snapshot.h1_score,
                h5_score=snapshot.h5_score,
                blend_score=getattr(snapshot, "blend_score", None),
                healthy_score_floor=healthy_score_floor,
                previous_h1_score=prev.get("h1_score"),  # type: ignore[arg-type]
                previous_h5_score=prev.get("h5_score"),  # type: ignore[arg-type]
                current_drop_threshold=current_drop_threshold,
                previous_drop_threshold=previous_drop_threshold,
            )
        )

    return candidates


def run_once_alert_service(
    config: AlertRunnerConfig,
    *,
    refresh_fn: Optional[RefreshFn] = None,
    telegram_sender: Optional[Sender] = None,
    now_utc: Optional[str] = None,
) -> AlertRunResult:
    telegram = _load_telegram_config(config)
    run_id = start_run(
        db_path=config.db_path,
        mode=telegram.mode,
        trigger_name=config.trigger_name,
        git_commit=config.git_commit,
        started_at_utc=now_utc,
        details={
            "ui_path": str(config.ui_path),
            "no_refresh": config.no_refresh,
        },
    )

    try:
        refresh_code = _run_refresh(config, refresh_fn)
        if refresh_code != 0:
            message = f"refresh failed with exit code {refresh_code}"
            add_system_event(
                db_path=config.db_path,
                run_id=run_id,
                event_type="refresh_failed",
                severity="error",
                message=message,
                ts_utc=now_utc,
                payload={"exit_code": refresh_code},
            )
            finish_run(
                db_path=config.db_path,
                run_id=run_id,
                status="failed",
                finished_at_utc=now_utc,
                details={"refresh_exit_code": refresh_code},
                error_text=message,
            )
            return AlertRunResult(
                exit_code=2, run_id=run_id, status="failed", error_text=message
            )

        previous = _read_previous_snapshots(
            db_path=config.db_path, before_run_id=run_id
        )
        ui_doc = load_ui_doc(config.ui_path)
        current_snapshots = collect_held_position_snapshots(ui_doc, ts_utc=now_utc)

        row_ids = write_held_position_snapshots(
            db_path=config.db_path,
            run_id=run_id,
            ui_doc=ui_doc,
            ts_utc=now_utc,
        )

        candidates = _detect_alerts(
            previous=previous,
            current_snapshots=current_snapshots,
            current_drop_threshold=config.current_drop_threshold,
            previous_drop_threshold=config.previous_drop_threshold,
            healthy_score_floor=config.healthy_score_floor,
        )
        history = read_alert_history_from_store(db_path=config.db_path)
        allowed, suppressed = apply_alert_cooldowns(
            candidates=candidates,
            history=history,
            now_utc=now_utc or "1970-01-01T00:00:00Z",
        )

        for candidate in allowed:
            kwargs = {}
            if telegram_sender is not None:
                kwargs["sender"] = telegram_sender
            send_and_record_alert_candidate(
                db_path=config.db_path,
                run_id=run_id,
                candidate=candidate,
                config=telegram,
                ts_utc=now_utc,
                **kwargs,
            )

        finish_run(
            db_path=config.db_path,
            run_id=run_id,
            status="success",
            finished_at_utc=now_utc,
            details={
                "snapshots_written": len(row_ids),
                "candidates": len(candidates),
                "allowed": len(allowed),
                "suppressed": len(suppressed),
            },
        )
        return AlertRunResult(
            exit_code=0,
            run_id=run_id,
            status="success",
            snapshots_written=len(row_ids),
            candidates_count=len(candidates),
            allowed_count=len(allowed),
            suppressed_count=len(suppressed),
        )

    except Exception as exc:
        message = str(exc)
        add_system_event(
            db_path=config.db_path,
            run_id=run_id,
            event_type="runner_failed",
            severity="error",
            message=message,
            ts_utc=now_utc,
        )
        finish_run(
            db_path=config.db_path,
            run_id=run_id,
            status="failed",
            finished_at_utc=now_utc,
            error_text=message,
        )
        return AlertRunResult(
            exit_code=1, run_id=run_id, status="failed", error_text=message
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the M43 alert service once.")
    parser.add_argument(
        "--db", type=Path, required=True, help="Path to alert SQLite database."
    )
    parser.add_argument(
        "--ui",
        type=Path,
        required=True,
        help="Path to market_health.ui.v1 JSON artifact.",
    )
    parser.add_argument(
        "--telegram-config",
        type=Path,
        default=None,
        help="Path to Telegram local config/secrets JSON.",
    )
    parser.add_argument(
        "--telegram-mode", choices=["disabled", "dry-run", "test", "live"], default=None
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip refresh command and use the existing UI artifact.",
    )
    parser.add_argument(
        "--refresh-cmd",
        default=" ".join(DEFAULT_REFRESH_CMD),
        help="Refresh command to run before loading artifacts.",
    )
    parser.add_argument("--trigger-name", default="manual")
    parser.add_argument("--git-commit", default=None)
    parser.add_argument(
        "--healthy-score-floor",
        type=float,
        default=55.0,
        help="Held-position healthy score floor for C/H1/H5/blend alerts.",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = AlertRunnerConfig(
        db_path=args.db,
        ui_path=args.ui,
        telegram_config_path=args.telegram_config,
        telegram_mode=args.telegram_mode,
        no_refresh=args.no_refresh,
        refresh_cmd=tuple(shlex.split(args.refresh_cmd)),
        trigger_name=args.trigger_name,
        git_commit=args.git_commit,
    )
    result = run_once_alert_service(config)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
