from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def default_db_path() -> Path:
    home = Path.home()
    candidates = [
        home / ".cache" / "jerboa" / "ledger.sqlite3",
        home / ".cache" / "jerboa" / "ledger.db",
        home / ".cache" / "jerboa" / "ledger" / "ledger.sqlite3",
        home / ".cache" / "jerboa" / "ledger" / "ledger.db",
        home / ".cache" / "jerboa" / "market_health.ledger.sqlite3",
        home / ".cache" / "jerboa" / "market_health.ledger.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Export market_health ledger SQLite -> JSONL"
    )
    ap.add_argument(
        "--db", type=Path, default=default_db_path(), help="Path to ledger sqlite db"
    )
    ap.add_argument(
        "--out", type=str, default="-", help="Output JSONL path or '-' for stdout"
    )
    ap.add_argument("--event-type", type=str, default=None, help="Filter by event_type")
    ap.add_argument(
        "--since", type=str, default=None, help="Filter ts_utc >= since (ISO string)"
    )
    ap.add_argument(
        "--until", type=str, default=None, help="Filter ts_utc <= until (ISO string)"
    )
    return ap.parse_args()


def open_out(out: str):
    if out == "-" or out.strip() == "":
        return sys.stdout, False
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p.open("w", encoding="utf-8"), True


def row_to_obj(row: tuple[Any, ...]) -> dict[str, Any]:
    _id, ts_utc, event_type, payload_json = row
    try:
        payload = json.loads(payload_json)
    except Exception:
        payload = payload_json
    return {
        "id": int(_id),
        "ts_utc": str(ts_utc),
        "event_type": str(event_type),
        "payload": payload,
    }


def main() -> int:
    args = parse_args()
    db: Path = args.db

    if not db.exists():
        raise SystemExit(f"Ledger db not found: {db} (use --db to point to it)")

    conn = sqlite3.connect(str(db))
    try:
        where: list[str] = []
        params: list[Any] = []

        if args.event_type:
            where.append("event_type = ?")
            params.append(args.event_type)

        if args.since:
            where.append("ts_utc >= ?")
            params.append(args.since)

        if args.until:
            where.append("ts_utc <= ?")
            params.append(args.until)

        sql = "SELECT id, ts_utc, event_type, payload_json FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts_utc ASC, id ASC"

        try:
            cur = conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            raise SystemExit(f"Ledger schema not found/invalid: {e}") from e

        out_f, should_close = open_out(args.out)
        try:
            for row in cur:
                obj = row_to_obj(row)
                out_f.write(json.dumps(obj, sort_keys=True) + "\n")
        finally:
            if should_close:
                out_f.close()

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
