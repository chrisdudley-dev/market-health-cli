from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_health.calibration.defaults import (
    assert_not_live_runtime_path,
    default_output_root,
)
from market_health.calibration.engine_metadata import capture_engine_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="market-health-calibration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate replay scaffold defaults.")
    doctor.add_argument("--out", type=Path, default=default_output_root())

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

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
