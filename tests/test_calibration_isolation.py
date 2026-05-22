from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.defaults import assert_not_live_runtime_path
from market_health.calibration.runner import run_fixture_replay


class CalibrationIsolationTest(unittest.TestCase):
    def test_common_live_runtime_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked_paths = [
                root / ".cache" / "jerboa" / "positions.v1.json",
                root / ".cache" / "jerboa" / "recommendations.v1.json",
                root / ".cache" / "jerboa" / "forecast_scores.v1.json",
                root / ".cache" / "jerboa" / "candidate" / "swap.json",
                root / ".cache" / "jerboa" / "swap" / "candidate.json",
                root / ".cache" / "jerboa" / "dashboard" / "latest.json",
                root / ".cache" / "jerboa" / "broker" / "positions.v1.json",
                root / ".cache" / "jerboa" / "runtime" / "state.json",
                root / ".cache" / "jerboa" / "alerts" / "alert_state.sqlite",
                root / ".config" / "jerboa" / "schwab_oauth.json",
            ]

            for path in blocked_paths:
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        assert_not_live_runtime_path(path)

    def test_calibration_output_path_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / ".cache" / "jerboa" / "calibration" / "m47"
            assert_not_live_runtime_path(output_root)

    def test_fixture_runner_rejects_live_runtime_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked_roots = [
                root / ".cache" / "jerboa" / "broker",
                root / ".cache" / "jerboa" / "runtime",
                root / ".cache" / "jerboa" / "alerts",
                root / ".config" / "jerboa",
            ]

            for output_root in blocked_roots:
                with self.subTest(output_root=output_root):
                    with self.assertRaises(ValueError):
                        run_fixture_replay(
                            output_root=output_root,
                            replay_dates=[date(2026, 5, 22)],
                            symbols=["SPY"],
                        )


if __name__ == "__main__":
    unittest.main()
