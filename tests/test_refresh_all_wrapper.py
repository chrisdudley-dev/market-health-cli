import json
import os
import subprocess
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_refresh_all_syncs_recommendations_from_ui_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    cache = tmp_path / ".cache" / "jerboa"
    bin_dir = tmp_path / "bin"
    cache.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    stale = {
        "schema": "recommendations.v1",
        "asof": "2026-07-25T00:00:00Z",
        "generated_at": "2026-07-25T00:00:00Z",
        "recommendation": {"asof": "2026-07-25T00:00:00Z"},
    }
    (cache / "recommendations.v1.json").write_text(
        json.dumps(stale, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (cache / "positions.v1.json").write_text(
        json.dumps({"schema": "positions.v1", "positions": []}) + "\n",
        encoding="utf-8",
    )

    _write_executable(
        bin_dir / "jerboa-market-health-refresh",
        """#!/usr/bin/env bash
set -Eeuo pipefail
cat > "${HOME}/.cache/jerboa/environment.v1.json" <<'JSON'
{"schema":"environment.v1","asof":"2026-07-26T15:00:00Z"}
JSON
cat > "${HOME}/.cache/jerboa/market_health.sectors.json" <<'JSON'
{"schema":"market_health.sectors.v1","asof":"2026-07-26T15:00:00Z"}
JSON
""",
    )
    _write_executable(
        bin_dir / "jerboa-market-health-ui-export",
        """#!/usr/bin/env bash
set -Eeuo pipefail
cat > "${HOME}/.cache/jerboa/market_health.ui.v1.json" <<'JSON'
{"schema":"jerboa.market_health.ui.v1","asof":"2026-07-26T16:00:00Z","status_line":"OK","meta":{},"summary":{},"data":{}}
JSON
""",
    )
    _write_executable(
        bin_dir / "jerboa-market-health-recommendations-refresh",
        """#!/usr/bin/env bash
set -Eeuo pipefail
exit 0
""",
    )

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        ["bash", "scripts/jerboa/bin/jerboa-market-health-refresh-all"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    rec = json.loads((cache / "recommendations.v1.json").read_text(encoding="utf-8"))
    assert rec["asof"] == "2026-07-26T16:00:00Z"
    assert rec["generated_at"] == "2026-07-26T16:00:00Z"
    assert rec["recommendation"]["asof"] == "2026-07-26T16:00:00Z"

    state = json.loads(
        (cache / "state" / "market_health_refresh_all.state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["status"] == "ok"
    assert state["changed"]["recommendations"] == 0
    assert "rec_changed=0" in result.stdout
