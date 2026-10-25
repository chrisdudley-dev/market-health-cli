from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import json
import math
import os
import re
import sqlite3
import sys

from market_health.engine_api import utc_now
from market_health.policy import evaluate, Scores
from market_health.policy.constants import POLICY_VERSION

DEFAULTS = {
    "net_liq": None,
    "cash": None,
    "target_positions": 8,
    "background": False,
    "interval": 15,
    "notify_sell": True,
    "notify_watch": True,
    "notify_hold": True,
    "notify_rescue": True,
    "notify_buy": False,
    "suppress_duplicates": True,
}
SYMBOL = re.compile(r"^[A-Z0-9^][A-Z0-9.^=\-]{0,24}$")


def app_data_dir():
    if sys.platform == "win32":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            / "MarketHealth"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/MarketHealth"
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        / "market-health"
    )


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else app_data_dir() / "market-health.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            v = db.execute("PRAGMA user_version").fetchone()[0]
            if v > 1:
                raise RuntimeError(
                    "Database was created by a newer Market Health version."
                )
            db.executescript("""
              CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY);
              CREATE TABLE IF NOT EXISTS holdings(
                symbol TEXT, account TEXT REFERENCES accounts(name), shares REAL NOT NULL,
                cost_basis REAL, notes TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol,account));
              CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS scans(
                id INTEGER PRIMARY KEY, scan_key TEXT UNIQUE NOT NULL, timestamp TEXT NOT NULL,
                source TEXT NOT NULL, status TEXT NOT NULL, error TEXT);
              CREATE TABLE IF NOT EXISTS decisions(
                id INTEGER PRIMARY KEY, scan_id INTEGER REFERENCES scans(id), timestamp TEXT,
                symbol TEXT, owned INTEGER, action TEXT, previous_action TEXT,
                accounts TEXT, scores TEXT, result TEXT, policy_version TEXT);
              CREATE TABLE IF NOT EXISTS transitions(
                id INTEGER PRIMARY KEY, decision_id INTEGER REFERENCES decisions(id),
                symbol TEXT, previous_action TEXT, action TEXT, timestamp TEXT);
              CREATE TABLE IF NOT EXISTS policy_state(
                symbol TEXT PRIMARY KEY, action TEXT, rescue_count INTEGER,
                buy_qualified INTEGER, owned INTEGER);
              CREATE TABLE IF NOT EXISTS notifications(
                id INTEGER PRIMARY KEY, decision_id INTEGER UNIQUE REFERENCES decisions(id),
                title TEXT, body TEXT, status TEXT DEFAULT 'pending', timestamp TEXT, error TEXT);
              CREATE TABLE IF NOT EXISTS portfolio_events(
                id INTEGER PRIMARY KEY, timestamp TEXT, event TEXT, payload TEXT);
              CREATE INDEX IF NOT EXISTS decisions_symbol_ts ON decisions(symbol,timestamp);
              PRAGMA user_version=1;
            """)
            for name in ("Roth IRA", "Individual", "Other"):
                db.execute("INSERT OR IGNORE INTO accounts VALUES(?)", (name,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connect() as db:
            return {
                **DEFAULTS,
                **{
                    r[0]: json.loads(r[1]) for r in db.execute("SELECT * FROM settings")
                },
            }

    def save_settings(self, values):
        merged = {**self.settings(), **values}
        if (
            type(merged["target_positions"]) is not int
            or merged["target_positions"] < 1
        ):
            raise ValueError("Target positions must be a positive integer.")
        if merged["interval"] not in (5, 10, 15, 30, 60):
            raise ValueError("Refresh interval must be 5, 10, 15, 30 or 60 minutes.")
        for k in ("net_liq", "cash"):
            v = merged[k]
            if v is not None and (
                type(v) not in (int, float) or not math.isfinite(v) or v < 0
            ):
                raise ValueError(k + " must be a finite nonnegative number or blank.")
        with self.connect() as db:
            for k, v in merged.items():
                if k in DEFAULTS:
                    db.execute(
                        "INSERT OR REPLACE INTO settings VALUES(?,?)",
                        (k, json.dumps(v)),
                    )

    def holdings(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM holdings ORDER BY symbol,account")
            ]

    def accounts(self):
        with self.connect() as db:
            return [r[0] for r in db.execute("SELECT name FROM accounts ORDER BY name")]

    def save_holding(
        self, symbol, account, shares, cost_basis=None, notes="", original=None
    ):
        symbol = symbol.strip().upper()
        account = account.strip() or "Other"
        if not SYMBOL.fullmatch(symbol):
            raise ValueError(
                "Enter a valid symbol (letters, digits, dot, dash or caret)."
            )
        if not math.isfinite(shares) or shares < 0:
            raise ValueError("Shares must be finite and nonnegative.")
        if cost_basis is not None and (not math.isfinite(cost_basis) or cost_basis < 0):
            raise ValueError("Cost basis must be finite and nonnegative.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if original and tuple(original) != (symbol, account):
                if db.execute(
                    "SELECT 1 FROM holdings WHERE symbol=? AND account=?",
                    (symbol, account),
                ).fetchone():
                    raise ValueError(
                        "That symbol/account already exists. Edit that holding directly."
                    )
                db.execute(
                    "DELETE FROM holdings WHERE symbol=? AND account=?", tuple(original)
                )
            db.execute("INSERT OR IGNORE INTO accounts VALUES(?)", (account,))
            db.execute(
                "INSERT OR REPLACE INTO holdings VALUES(?,?,?,?,?,?)",
                (symbol, account, shares, cost_basis, notes, utc_now()),
            )
            db.execute(
                "INSERT INTO portfolio_events(timestamp,event,payload) VALUES(?,?,?)",
                (
                    utc_now(),
                    "save",
                    json.dumps(dict(symbol=symbol, account=account, shares=shares)),
                ),
            )
            # A new ownership period must not inherit a former rescue streak.
            db.execute(
                "DELETE FROM policy_state WHERE symbol NOT IN (SELECT symbol FROM holdings) AND owned=1"
            )
            db.execute("DELETE FROM policy_state WHERE symbol=? AND owned=0", (symbol,))

    def remove_holding(self, symbol, account):
        with self.connect() as db:
            db.execute(
                "DELETE FROM holdings WHERE symbol=? AND account=?", (symbol, account)
            )
            if not db.execute(
                "SELECT 1 FROM holdings WHERE symbol=?", (symbol,)
            ).fetchone():
                db.execute("DELETE FROM policy_state WHERE symbol=?", (symbol,))
            db.execute(
                "INSERT INTO portfolio_events(timestamp,event,payload) VALUES(?,?,?)",
                (utc_now(), "remove", json.dumps(dict(symbol=symbol, account=account))),
            )

    def record_failure(self, error):
        with self.connect() as db:
            db.execute(
                "INSERT INTO scans(scan_key,timestamp,source,status,error) VALUES(?,?,?,?,?)",
                (utc_now(), utc_now(), "refresh", "error", error),
            )

    def apply_scan(self, scan):
        settings = self.settings()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM scans WHERE scan_key=?", (scan.key,)
            ).fetchone():
                return (
                    False  # duplicate snapshot import cannot consume a rescue refresh
                )
            if not scan.rows or len({s.symbol for s in scan.rows}) != len(scan.rows):
                raise ValueError("A scan must have unique, nonempty rows.")
            owned = {
                r[0]: [] for r in db.execute("SELECT DISTINCT symbol FROM holdings")
            }
            for r in db.execute("SELECT symbol,account FROM holdings"):
                owned[r[0]].append(r[1])
            rows = list(scan.rows)
            rows.extend(
                Scores(s, error="Owned symbol was absent from scan.")
                for s in owned
                if s not in {r.symbol for r in rows}
            )
            status = "partial" if any(s.error for s in rows) else "ok"
            scan_id = db.execute(
                "INSERT INTO scans(scan_key,timestamp,source,status) VALUES(?,?,?,?)",
                (scan.key, scan.timestamp, scan.source, status),
            ).lastrowid
            for s in rows:
                is_owned = s.symbol in owned
                prev = db.execute(
                    "SELECT * FROM policy_state WHERE symbol=?", (s.symbol,)
                ).fetchone()
                rescue = (
                    prev["rescue_count"] if prev and is_owned and prev["owned"] else 0
                )
                d = evaluate(
                    s,
                    owned=is_owned,
                    previous_rescue_count=rescue,
                    timestamp=scan.timestamp,
                )
                previous = prev["action"] if prev else None
                decision_id = db.execute(
                    """INSERT INTO decisions(scan_id,timestamp,symbol,owned,action,
                    previous_action,accounts,scores,result,policy_version) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        scan_id,
                        scan.timestamp,
                        s.symbol,
                        int(is_owned),
                        d.action,
                        previous,
                        json.dumps(owned.get(s.symbol, [])),
                        json.dumps(asdict(s)),
                        json.dumps(asdict(d)),
                        POLICY_VERSION,
                    ),
                ).lastrowid
                if d.action == "DATA ERROR":
                    db.execute(
                        "UPDATE scans SET status='partial' WHERE id=?", (scan_id,)
                    )
                    continue  # preserve last valid action and rescue; no erroneous recovery notification
                changed = (
                    prev is not None
                    and previous != d.action
                    and bool(prev["owned"]) == is_owned
                )
                if changed:
                    db.execute(
                        "INSERT INTO transitions(decision_id,symbol,previous_action,action,timestamp) VALUES(?,?,?,?,?)",
                        (decision_id, s.symbol, previous, d.action, scan.timestamp),
                    )
                toggle = {
                    "SELL": "notify_sell",
                    "WATCH": "notify_watch",
                    "HOLD": "notify_hold",
                    "HOLD — RESCUE": "notify_rescue",
                }.get(d.action)
                notify_owned = is_owned and changed and toggle and settings[toggle]
                notify_buy = (
                    not is_owned
                    and d.buy_qualified
                    and (prev is None or not prev["buy_qualified"])
                    and settings["notify_buy"]
                )
                # Transition-only semantics are unconditional. The preference cannot
                # cause repeated SELL->SELL alerts or relax the policy.
                if (notify_owned or notify_buy) and scan.source == "live engine":
                    body = (
                        f"{previous} → {d.action}\nC: {s.c:g}  H1: {s.h1:g}  H5: {s.h5:g}  Blend: {s.blend:g}\n"
                        + d.human_explanation
                    )
                    db.execute(
                        "INSERT INTO notifications(decision_id,title,body,timestamp) VALUES(?,?,?,?)",
                        (
                            decision_id,
                            "Market Health — " + s.symbol,
                            body,
                            scan.timestamp,
                        ),
                    )
                db.execute(
                    "INSERT OR REPLACE INTO policy_state VALUES(?,?,?,?,?)",
                    (
                        s.symbol,
                        d.action,
                        d.rescue_count,
                        int(d.buy_qualified),
                        int(is_owned),
                    ),
                )
        return True

    def latest(self):
        with self.connect() as db:
            sid = db.execute(
                "SELECT MAX(id) FROM scans WHERE status IN ('ok','partial')"
            ).fetchone()[0]
            return [
                self._decision(r)
                for r in db.execute(
                    "SELECT * FROM decisions WHERE scan_id=? ORDER BY symbol", (sid,)
                )
            ]

    @staticmethod
    def _decision(r):
        row = dict(r)
        for k in ("accounts", "scores", "result"):
            row[k] = json.loads(row[k])
        return row

    def history(
        self, symbol="", action="", account="", date="", *, limit=None, before_id=None
    ):
        clauses, values = [], []
        for expression, value in (
            ("instr(upper(symbol),?) > 0", symbol.upper()),
            ("action=?", action),
            ("instr(accounts,?) > 0", json.dumps(account) if account else ""),
            ("substr(timestamp,1,10)=?", date),
        ):
            if value:
                clauses.append(expression)
                values.append(value)
        if before_id is not None:
            clauses.append("id < ?")
            values.append(int(before_id))
        sql = (
            "SELECT * FROM decisions"
            + (" WHERE " + " AND ".join(clauses) if clauses else "")
            + " ORDER BY id DESC"
        )
        if limit is not None:
            if int(limit) < 1:
                raise ValueError("History page size must be positive.")
            sql += " LIMIT ?"
            values.append(int(limit))
        with self.connect() as db:
            return [self._decision(r) for r in db.execute(sql, values)]

    def status(self):
        with self.connect() as db:
            r = db.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            return dict(r) if r else None

    def pending_notifications(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM notifications WHERE status='pending'"
                )
            ]

    def mark_notification(self, notification_id, status, error=""):
        with self.connect() as db:
            db.execute(
                "UPDATE notifications SET status=?,error=? WHERE id=?",
                (status, error, notification_id),
            )
