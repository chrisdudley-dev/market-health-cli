from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class EngineMetadata:
    schema_version: str
    generated_at: str
    repo_root: str
    git_commit: str
    git_dirty: bool


def _git(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def capture_engine_metadata(repo_root: Path | None = None) -> dict[str, object]:
    """Capture deterministic replay provenance metadata."""
    root = (repo_root or Path.cwd()).resolve()
    status = _git(root, "status", "--porcelain")
    return asdict(
        EngineMetadata(
            schema_version="calibration_engine_metadata.v1",
            generated_at=datetime.now(timezone.utc).isoformat(),
            repo_root=str(root),
            git_commit=_git(root, "rev-parse", "HEAD"),
            git_dirty=bool(status and status != "unknown"),
        )
    )
