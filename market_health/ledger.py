from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def connect(db_path: Path) -> sqlite3.Connection:
    _ensure_parent(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def apply_migrations(conn: sqlite3.Connection) -> None:
    v = _current_version(conn)

    if v < 1:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts_utc)"
        )
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
            (1, _utc_now_iso()),
        )
        conn.commit()


def append_event(
    *,
    db_path: Path,
    event_type: str,
    payload: Dict[str, Any],
    ts_utc: Optional[str] = None,
) -> None:
    """Append an event row."""
    ts = ts_utc or _utc_now_iso()
    with connect(db_path) as conn:
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO events(ts_utc, event_type, payload_json) VALUES(?, ?, ?)",
            (ts, event_type, json.dumps(payload, sort_keys=True)),
        )
        conn.commit()


def read_events(db_path: Path, *, limit: int = 1000) -> List[Dict[str, Any]]:
    with connect(db_path) as conn:
        apply_migrations(conn)
        rows = conn.execute(
            "SELECT id, ts_utc, event_type, payload_json FROM events ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for id_, ts, et, pj in rows:
        out.append(
            {
                "id": int(id_),
                "ts_utc": str(ts),
                "event_type": str(et),
                "payload": json.loads(pj),
            }
        )
    return out
