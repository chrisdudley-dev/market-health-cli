import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _mk_db(p: Path) -> None:
    conn = sqlite3.connect(str(p))
    try:
        conn.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO events(ts_utc, event_type, payload_json) VALUES(?, ?, ?)",
            ("2026-02-22T00:00:00Z", "recommendation", json.dumps({"a": 1})),
        )
        conn.execute(
            "INSERT INTO events(ts_utc, event_type, payload_json) VALUES(?, ?, ?)",
            ("2026-02-23T00:00:00Z", "refresh", json.dumps({"b": 2})),
        )
        conn.commit()
    finally:
        conn.close()


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/export_ledger_jsonl_v0.py", *args],
        check=True,
        text=True,
        capture_output=True,
    )


def test_export_jsonl_stdout(tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite3"
    _mk_db(db)

    p = _run(["--db", str(db), "--out", "-"])
    lines = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]

    assert [x["event_type"] for x in lines] == ["recommendation", "refresh"]
    assert lines[0]["payload"] == {"a": 1}


def test_export_filters(tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite3"
    _mk_db(db)

    p = _run(["--db", str(db), "--out", "-", "--event-type", "refresh"])
    lines = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    assert len(lines) == 1
    assert lines[0]["event_type"] == "refresh"

    p = _run(["--db", str(db), "--out", "-", "--since", "2026-02-23T00:00:00Z"])
    lines = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    assert len(lines) == 1
    assert lines[0]["ts_utc"] == "2026-02-23T00:00:00Z"


def test_export_to_file(tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite3"
    _mk_db(db)

    out = tmp_path / "out.jsonl"
    _run(["--db", str(db), "--out", str(out)])

    txt = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(txt) == 2
