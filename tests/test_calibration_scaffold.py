from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from market_health.calibration.cli import main
from market_health.calibration.defaults import (
    assert_not_live_runtime_path,
    default_output_root,
)
from market_health.calibration.engine_metadata import capture_engine_metadata
from market_health.calibration.schema import (
    REPLAY_ARTIFACT_SCHEMA_VERSION,
    ReplayArtifactRow,
)


class CalibrationScaffoldTest(unittest.TestCase):
    def test_default_output_root_uses_isolated_calibration_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
                self.assertEqual(
                    default_output_root(),
                    Path(tmp) / "jerboa" / "calibration" / "m47",
                )

    def test_live_runtime_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked_paths = [
                root / ".cache" / "jerboa" / "positions.v1.json",
                root / ".cache" / "jerboa" / "recommendations.v1.json",
                root / ".cache" / "jerboa" / "forecast_scores.v1.json",
                root / ".config" / "jerboa" / "schwab_oauth.json",
            ]

            for path in blocked_paths:
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        assert_not_live_runtime_path(path)

    def test_engine_metadata_shape(self) -> None:
        metadata = capture_engine_metadata()

        self.assertEqual(
            metadata["schema_version"],
            "calibration_engine_metadata.v1",
        )
        self.assertIsInstance(metadata["generated_at"], str)
        self.assertIsInstance(metadata["repo_root"], str)
        self.assertIsInstance(metadata["git_commit"], str)
        self.assertIsInstance(metadata["git_dirty"], bool)

    def test_replay_artifact_row_record_shape(self) -> None:
        row = ReplayArtifactRow(
            replay_date=date(2026, 5, 22),
            symbol="SPY",
            current_score=8.0,
            h1_score=8.5,
            h5_score=7.5,
            blend_score=8.1,
            state="GREEN",
            audit_token="A=888:111111",
        )

        record = row.to_record()

        self.assertEqual(record["schema_version"], REPLAY_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(record["replay_date"], "2026-05-22")
        self.assertEqual(record["symbol"], "SPY")
        self.assertEqual(record["audit_token"], "A=888:111111")

    def test_doctor_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(main(["doctor"]), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["output_root"].endswith("jerboa/calibration/m47"))
        self.assertEqual(
            payload["engine"]["schema_version"],
            "calibration_engine_metadata.v1",
        )


if __name__ == "__main__":
    unittest.main()
