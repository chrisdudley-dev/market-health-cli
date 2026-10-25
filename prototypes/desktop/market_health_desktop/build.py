"""python -m market_health.desktop.build"""

from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[2]
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            str(root / "packaging/MarketHealth.spec"),
        ],
        cwd=root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
