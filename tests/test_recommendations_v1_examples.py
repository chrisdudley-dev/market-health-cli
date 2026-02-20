from pathlib import Path
import subprocess


def _run(path: str) -> str:
    p = subprocess.run(
        ["python", "scripts/validate_recommendations_v1.py", "--path", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return p.stdout


def test_examples_validate():
    base = Path("docs/examples")
    out1 = _run(str(base / "recommendations.v1.swap.json"))
    out2 = _run(str(base / "recommendations.v1.noop.json"))
    assert "OK: recommendations.v1 valid" in out1
    assert "OK: recommendations.v1 valid" in out2
