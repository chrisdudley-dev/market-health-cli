"""Terminal view of the same refresh/policy/database used by the desktop app."""

import argparse
import json
from pathlib import Path
import time

from rich.console import Console
from rich.table import Table
from market_health.storage.sqlite import Store
from market_health.application.service import RefreshService


def main():
    parser = argparse.ArgumentParser(description="Market Health · local MH Policy")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument(
        "--ohlcv",
        type=Path,
        help="Explicit local OHLCV document for the shared calculation boundary",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--out", type=Path, help="Export current decisions as JSON")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--watch", type=int, default=0, help="Refresh every N seconds")
    parser.add_argument(
        "--pi-grid", action="store_true", help="Compact terminal score table"
    )
    parser.add_argument("--grid-cols", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--mono", action="store_true")
    args = parser.parse_args()
    store = Store(args.database)
    console = Console(no_color=args.mono)
    while True:
        if args.refresh or args.snapshot or args.ohlcv or args.watch:
            try:
                if args.ohlcv:
                    RefreshService(store).refresh_document(
                        json.loads(args.ohlcv.read_text()),
                        source="local OHLCV (historical)",
                    )
                else:
                    RefreshService(store).refresh(args.snapshot)
            except Exception as exc:
                console.print("STALE · " + str(exc), style="red", markup=False)
                return 1
        if args.status:
            console.print_json(data=store.status() or {"status": "no scans"})
        rows = store.latest()
        if args.out:
            args.out.write_text(
                json.dumps({"schema": "mh-policy.v1", "decisions": rows}, indent=2)
                + "\n",
                encoding="utf-8",
            )
        table = Table(title="Market Health · local MH Policy", expand=True)
        for label in ("Symbol", "Owned", "Blend", "C", "H1", "H5", "State", "Action"):
            table.add_column(label)
        owned = {h["symbol"] for h in store.holdings()}
        for r in rows:
            sc = r["scores"]
            action = (
                r["action"]
                if bool(r["owned"]) == (r["symbol"] in owned)
                else "PENDING REFRESH"
            )
            table.add_row(
                r["symbol"],
                "yes" if r["symbol"] in owned else "—",
                *[
                    "—" if sc.get(k) is None else f"{sc[k]:.2f}"
                    for k in ("blend", "c", "h1", "h5")
                ],
                sc["state"],
                action,
            )
        console.print(table)
        if not rows:
            console.print(
                "Use --refresh to fetch scores, or launch market-health-desktop."
            )
        if args.watch <= 0:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main())
