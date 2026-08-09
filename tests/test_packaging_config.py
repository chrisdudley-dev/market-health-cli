from __future__ import annotations

import tomllib
from pathlib import Path

from setuptools import find_packages


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _load_pyproject() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _market_health_packages() -> set[str]:
    packages: set[str] = set()
    for init_file in (ROOT / "market_health").glob("**/__init__.py"):
        packages.add(".".join(init_file.parent.relative_to(ROOT).parts))
    return packages


def _discovered_market_health_packages() -> set[str]:
    return set(
        find_packages(
            where=str(ROOT),
            include=["market_health*"],
            exclude=["tests*"],
        )
    )


def test_setuptools_discovers_all_market_health_packages() -> None:
    pyproject = _load_pyproject()
    setuptools = pyproject["tool"]["setuptools"]

    assert setuptools["py-modules"] == ["market_ui"]

    package_find = setuptools["packages"]["find"]
    assert setuptools["packages"] == {
        "find": {
            "include": ["market_health*"],
            "exclude": ["tests*"],
        }
    }
    assert package_find["include"] == ["market_health*"]
    assert package_find.get("exclude", []) == ["tests*"]

    expected_packages = _market_health_packages()
    assert _discovered_market_health_packages() == expected_packages
    assert expected_packages == {
        "market_health",
        "market_health.brokers",
        "market_health.calibration",
        "market_health.providers",
    }


def test_console_scripts_remain_intact() -> None:
    project = _load_pyproject()["project"]

    assert project["scripts"] == {
        "market-health": "market_health.dashboard_legacy:main",
        "market-health-pi": "market_health.dashboard_legacy:main",
        "mh": "market_health.dashboard_legacy:main",
    }
