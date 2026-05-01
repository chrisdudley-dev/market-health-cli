from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from market_health.alert_store import apply_migrations, connect

SERVICE_NAME = "jerboa-market-health-alert.service"
TIMER_NAME = "jerboa-market-health-alert.timer"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[[Sequence[str]], CommandResult]


def _default_command_runner(cmd: Sequence[str]) -> CommandResult:
    try:
        proc = subprocess.run(
            list(cmd),
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        return CommandResult(returncode=127, stderr=str(exc))
    return CommandResult(
        returncode=proc.returncode,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
    )


def _db_size(db_path: Path) -> int:
    return db_path.stat().st_size if db_path.exists() else 0


def _one(conn, sql: str):
    return conn.execute(sql).fetchone()


def _sqlite_status(db_path: Path) -> dict:
    status = {
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "db_size_bytes": _db_size(db_path),
        "last_run": None,
        "last_successful_run": None,
        "last_failed_run": None,
        "latest_positions_timestamp": None,
        "latest_forecast_timestamp": None,
        "latest_telegram_alert": None,
        "latest_system_health_event": None,
    }

    if not db_path.exists():
        return status

    with connect(db_path) as conn:
        apply_migrations(conn)

        status["last_run"] = dict(
            _one(
                conn,
                """
                SELECT id, started_at_utc, finished_at_utc, status, mode, trigger_name, error_text
                FROM runs
                ORDER BY id DESC
                LIMIT 1
                """,
            )
            or {}
        )
        status["last_successful_run"] = dict(
            _one(
                conn,
                """
                SELECT id, started_at_utc, finished_at_utc, status, mode, trigger_name
                FROM runs
                WHERE status = 'success'
                ORDER BY id DESC
                LIMIT 1
                """,
            )
            or {}
        )
        status["last_failed_run"] = dict(
            _one(
                conn,
                """
                SELECT id, started_at_utc, finished_at_utc, status, mode, trigger_name, error_text
                FROM runs
                WHERE status != 'success'
                ORDER BY id DESC
                LIMIT 1
                """,
            )
            or {}
        )
        latest_positions = _one(
            conn,
            """
            SELECT MAX(ts_utc) AS ts_utc
            FROM symbol_snapshots
            WHERE is_held = 1
            """,
        )
        status["latest_positions_timestamp"] = (
            latest_positions["ts_utc"] if latest_positions else None
        )

        latest_forecast = _one(
            conn,
            """
            SELECT MAX(ts_utc) AS ts_utc
            FROM symbol_snapshots
            WHERE h1_score IS NOT NULL OR h5_score IS NOT NULL
            """,
        )
        status["latest_forecast_timestamp"] = (
            latest_forecast["ts_utc"] if latest_forecast else None
        )

        latest_alert = _one(
            conn,
            """
            SELECT id, ts_utc, alert_key, alert_type, severity, symbol,
                   delivery_status, delivered_at_utc, error_text
            FROM alerts
            ORDER BY id DESC
            LIMIT 1
            """,
        )
        status["latest_telegram_alert"] = dict(latest_alert or {})

        latest_system = _one(
            conn,
            """
            SELECT id, ts_utc, event_type, severity, message
            FROM system_events
            ORDER BY id DESC
            LIMIT 1
            """,
        )
        status["latest_system_health_event"] = dict(latest_system or {})

    return status


def _systemd_unit_status(
    *,
    unit_name: str,
    runner: CommandRunner,
) -> dict:
    cat = runner(["systemctl", "--user", "cat", unit_name])
    enabled = runner(["systemctl", "--user", "is-enabled", unit_name])
    active = runner(["systemctl", "--user", "is-active", unit_name])

    if cat.returncode == 127 or enabled.returncode == 127 or active.returncode == 127:
        return {
            "unit": unit_name,
            "systemd_available": False,
            "installed": None,
            "enabled": None,
            "active": None,
        }

    return {
        "unit": unit_name,
        "systemd_available": True,
        "installed": cat.returncode == 0,
        "enabled": enabled.stdout.strip() or "unknown",
        "active": active.stdout.strip() or "unknown",
    }


def _git_commit(repo_path: Path, runner: CommandRunner) -> Optional[str]:
    result = runner(["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def build_alert_status(
    *,
    db_path: Path,
    repo_path: Path,
    runner: CommandRunner = _default_command_runner,
) -> dict:
    return {
        "service": _systemd_unit_status(unit_name=SERVICE_NAME, runner=runner),
        "timer": _systemd_unit_status(unit_name=TIMER_NAME, runner=runner),
        "database": _sqlite_status(db_path),
        "git_commit": _git_commit(repo_path, runner),
    }


def _format_optional_run(run: Optional[dict]) -> str:
    if not run:
        return "none"
    return (
        f"id={run.get('id')} status={run.get('status')} "
        f"started={run.get('started_at_utc')} finished={run.get('finished_at_utc')} "
        f"mode={run.get('mode')} trigger={run.get('trigger_name')}"
    )


def format_status_text(status: dict) -> str:
    db = status["database"]
    service = status["service"]
    timer = status["timer"]
    latest_alert = db.get("latest_telegram_alert") or {}
    latest_system = db.get("latest_system_health_event") or {}

    lines = [
        "m43-alert-status:",
        f"  service: installed={service.get('installed')} enabled={service.get('enabled')} active={service.get('active')}",
        f"  timer: installed={timer.get('installed')} enabled={timer.get('enabled')} active={timer.get('active')}",
        f"  database: path={db.get('db_path')} exists={db.get('db_exists')} size_bytes={db.get('db_size_bytes')}",
        f"  git_commit: {status.get('git_commit') or 'unknown'}",
        f"  last_run: {_format_optional_run(db.get('last_run'))}",
        f"  last_successful_run: {_format_optional_run(db.get('last_successful_run'))}",
        f"  last_failed_run: {_format_optional_run(db.get('last_failed_run'))}",
        f"  latest_positions_timestamp: {db.get('latest_positions_timestamp') or 'none'}",
        f"  latest_forecast_timestamp: {db.get('latest_forecast_timestamp') or 'none'}",
        (
            "  latest_telegram_alert: "
            f"id={latest_alert.get('id', 'none')} "
            f"type={latest_alert.get('alert_type', 'none')} "
            f"status={latest_alert.get('delivery_status', 'none')} "
            f"ts={latest_alert.get('ts_utc', 'none')}"
        ),
        (
            "  latest_system_health_event: "
            f"id={latest_system.get('id', 'none')} "
            f"type={latest_system.get('event_type', 'none')} "
            f"severity={latest_system.get('severity', 'none')} "
            f"ts={latest_system.get('ts_utc', 'none')}"
        ),
    ]
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Show M43 alert-service status.")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path.home() / ".cache/jerboa/market_health_alerts.v1.sqlite",
        help="Path to alert SQLite database.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Path to market-health-cli git checkout.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON status.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    status = build_alert_status(db_path=args.db, repo_path=args.repo)

    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(format_status_text(status))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
