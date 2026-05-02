from __future__ import annotations

import ast
from pathlib import Path


def test_direct_forecast_checks_have_explicit_source_quality_and_fallback() -> None:
    missing: list[str] = []

    for path in sorted(Path("market_health").glob("forecast_checks_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr

            if name != "ForecastCheck":
                continue

            keys = {kw.arg for kw in node.keywords if kw.arg}
            if "source_quality" not in keys or "fallback_used" not in keys:
                missing.append(f"{path}:{node.lineno}")

    assert missing == []


def test_forecast_source_quality_values_are_known() -> None:
    allowed = {"real", "proxy", "neutral", "disabled", "direct"}
    bad: list[str] = []

    for path in sorted(Path("market_health").glob("forecast_checks_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr

            if name != "ForecastCheck":
                continue

            for kw in node.keywords:
                if kw.arg != "source_quality":
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(
                    kw.value.value, str
                ):
                    if kw.value.value not in allowed:
                        bad.append(f"{path}:{node.lineno}:{kw.value.value}")
                else:
                    bad.append(f"{path}:{node.lineno}:non-literal")

    assert bad == []
