from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Set

SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _json_dumps(value: Optional[Dict[str, Any]]) -> str:
    return json.dumps(value or {}, sort_keys=True)


def connect(db_path: Path) -> sqlite3.Connection:
    _ensure_parent(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at_utc TEXT NOT NULL
        )
        """
    )
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def apply_migrations(conn: sqlite3.Connection) -> None:
    version = _current_version(conn)

    if version < 1:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                trigger_name TEXT NOT NULL,
                git_commit TEXT,
                details_json TEXT NOT NULL DEFAULT '{}',
                error_text TEXT
            );

            CREATE TABLE IF NOT EXISTS symbol_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                ts_utc TEXT NOT NULL,
                symbol TEXT NOT NULL,
                is_held INTEGER NOT NULL DEFAULT 1,
                current_score REAL,
                blend_score REAL,
                h1_score REAL,
                h5_score REAL,
                state TEXT,
                stop_price REAL,
                buy_price REAL,
                sup_atr REAL,
                res_atr REAL,
                last_price REAL,
                source_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                ts_utc TEXT NOT NULL,
                alert_key TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                symbol TEXT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                delivery_status TEXT NOT NULL DEFAULT 'pending',
                delivered_at_utc TEXT,
                error_text TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                ts_utc TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                ts_utc TEXT NOT NULL,
                export_type TEXT NOT NULL,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                path TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                error_text TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS daily_digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_date TEXT NOT NULL UNIQUE,
                created_at_utc TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                error_text TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_runs_started
                ON runs(started_at_utc);

            CREATE INDEX IF NOT EXISTS idx_symbol_snapshots_run_symbol
                ON symbol_snapshots(run_id, symbol);

            CREATE INDEX IF NOT EXISTS idx_symbol_snapshots_symbol_ts
                ON symbol_snapshots(symbol, ts_utc);

            CREATE INDEX IF NOT EXISTS idx_alerts_key_ts
                ON alerts(alert_key, ts_utc);

            CREATE INDEX IF NOT EXISTS idx_alerts_type_symbol_ts
                ON alerts(alert_type, symbol, ts_utc);

            CREATE INDEX IF NOT EXISTS idx_system_events_type_ts
                ON system_events(event_type, ts_utc);

            CREATE INDEX IF NOT EXISTS idx_exports_type_ts
                ON exports(export_type, ts_utc);
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES(?, ?)",
            (1, _utc_now_iso()),
        )
        conn.commit()


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        apply_migrations(conn)


def table_names(db_path: Path) -> Set[str]:
    with connect(db_path) as conn:
        apply_migrations(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {str(row["name"]) for row in rows}


def start_run(
    *,
    db_path: Path,
    mode: str,
    trigger_name: str,
    git_commit: Optional[str] = None,
    started_at_utc: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    ts = started_at_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        cur = conn.execute(
            """
            INSERT INTO runs(
                started_at_utc,
                status,
                mode,
                trigger_name,
                git_commit,
                details_json
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (ts, "running", mode, trigger_name, git_commit, _json_dumps(details)),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_run(
    *,
    db_path: Path,
    run_id: int,
    status: str,
    finished_at_utc: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    error_text: Optional[str] = None,
) -> None:
    ts = finished_at_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        conn.execute(
            """
            UPDATE runs
            SET finished_at_utc = ?,
                status = ?,
                details_json = ?,
                error_text = ?
            WHERE id = ?
            """,
            (ts, status, _json_dumps(details), error_text, int(run_id)),
        )
        conn.commit()


def add_symbol_snapshot(
    *,
    db_path: Path,
    run_id: int,
    symbol: str,
    ts_utc: Optional[str] = None,
    is_held: bool = True,
    current_score: Optional[float] = None,
    blend_score: Optional[float] = None,
    h1_score: Optional[float] = None,
    h5_score: Optional[float] = None,
    state: Optional[str] = None,
    stop_price: Optional[float] = None,
    buy_price: Optional[float] = None,
    sup_atr: Optional[float] = None,
    res_atr: Optional[float] = None,
    last_price: Optional[float] = None,
    source: Optional[Dict[str, Any]] = None,
) -> int:
    ts = ts_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        cur = conn.execute(
            """
            INSERT INTO symbol_snapshots(
                run_id,
                ts_utc,
                symbol,
                is_held,
                current_score,
                blend_score,
                h1_score,
                h5_score,
                state,
                stop_price,
                buy_price,
                sup_atr,
                res_atr,
                last_price,
                source_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(run_id),
                ts,
                symbol,
                1 if is_held else 0,
                current_score,
                blend_score,
                h1_score,
                h5_score,
                state,
                stop_price,
                buy_price,
                sup_atr,
                res_atr,
                last_price,
                _json_dumps(source),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def add_alert(
    *,
    db_path: Path,
    alert_key: str,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    run_id: Optional[int] = None,
    symbol: Optional[str] = None,
    ts_utc: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    delivery_status: str = "pending",
    delivered_at_utc: Optional[str] = None,
    error_text: Optional[str] = None,
) -> int:
    ts = ts_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        cur = conn.execute(
            """
            INSERT INTO alerts(
                run_id,
                ts_utc,
                alert_key,
                alert_type,
                severity,
                symbol,
                title,
                message,
                payload_json,
                delivery_status,
                delivered_at_utc,
                error_text
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                ts,
                alert_key,
                alert_type,
                severity,
                symbol,
                title,
                message,
                _json_dumps(payload),
                delivery_status,
                delivered_at_utc,
                error_text,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def add_system_event(
    *,
    db_path: Path,
    event_type: str,
    severity: str,
    message: str,
    run_id: Optional[int] = None,
    ts_utc: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> int:
    ts = ts_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        cur = conn.execute(
            """
            INSERT INTO system_events(
                run_id,
                ts_utc,
                event_type,
                severity,
                message,
                payload_json
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (run_id, ts, event_type, severity, message, _json_dumps(payload)),
        )
        conn.commit()
        return int(cur.lastrowid)


def add_export(
    *,
    db_path: Path,
    export_type: str,
    target: str,
    status: str,
    run_id: Optional[int] = None,
    ts_utc: Optional[str] = None,
    path: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    error_text: Optional[str] = None,
) -> int:
    ts = ts_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        cur = conn.execute(
            """
            INSERT INTO exports(
                run_id,
                ts_utc,
                export_type,
                target,
                status,
                path,
                payload_json,
                error_text
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                ts,
                export_type,
                target,
                status,
                path,
                _json_dumps(payload),
                error_text,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def add_daily_digest(
    *,
    db_path: Path,
    digest_date: str,
    status: str,
    created_at_utc: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    error_text: Optional[str] = None,
) -> int:
    ts = created_at_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        cur = conn.execute(
            """
            INSERT INTO daily_digests(
                digest_date,
                created_at_utc,
                status,
                payload_json,
                error_text
            )
            VALUES(?, ?, ?, ?, ?)
            """,
            (digest_date, ts, status, _json_dumps(payload), error_text),
        )
        conn.commit()
        return int(cur.lastrowid)


def count_rows(db_path: Path, table: str) -> int:
    allowed = {
        "runs",
        "symbol_snapshots",
        "alerts",
        "system_events",
        "exports",
        "daily_digests",
        "schema_migrations",
    }
    if table not in allowed:
        raise ValueError(f"unsupported table: {table}")

    with connect(db_path) as conn:
        apply_migrations(conn)
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])
