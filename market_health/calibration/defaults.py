from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RELATIVE_OUTPUT_ROOT = Path("jerboa") / "calibration" / "m47"

LIVE_RUNTIME_PATH_MARKERS = (
    "/.cache/jerboa/positions",
    "/.cache/jerboa/recommendations",
    "/.cache/jerboa/forecast_scores",
    "/.cache/jerboa/candidate",
    "/.cache/jerboa/swap",
    "/.cache/jerboa/dashboard",
    "/.config/jerboa",
)


def default_output_root() -> Path:
    """Return the default isolated calibration output root."""
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache_home).expanduser() if xdg_cache_home else Path.home() / ".cache"
    return base / DEFAULT_RELATIVE_OUTPUT_ROOT


def assert_not_live_runtime_path(path: Path) -> None:
    """Reject output paths that target live runtime or production state."""
    resolved = path.expanduser().resolve()
    text = str(resolved)

    if any(marker in text for marker in LIVE_RUNTIME_PATH_MARKERS):
        raise ValueError(
            "calibration replay output must not target live runtime state: "
            f"{resolved}"
        )
