import json
import os
import subprocess
import tempfile
from pathlib import Path
from shutil import copyfile


def _run_ui_export_from_fixture(tmp_home: Path, scenario_dir: Path) -> dict:
    cache = tmp_home / ".cache" / "jerboa"
    (cache / "state").mkdir(parents=True, exist_ok=True)

    for f in scenario_dir.glob("*.json"):
        copyfile(f, cache / f.name)
    for f in (scenario_dir / "state").glob("*.json"):
        copyfile(f, cache / "state" / f.name)

    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    env["QUIET"] = "1"
    env.setdefault("JERBOA_PYTHON", "python")

    subprocess.run(
        ["bash", "scripts/jerboa/bin/jerboa-market-health-ui-export"],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    p = cache / "market_health.ui.v1.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _sector_totals(contract: dict) -> dict[str, int]:
    sectors = contract.get("data", {}).get("sectors") or []
    out: dict[str, int] = {}
    for s in sectors:
        if not isinstance(s, dict):
            continue
        sym = s.get("symbol")
        if not isinstance(sym, str):
            continue

        # Prefer explicit total if present; else compute from categories/checks
        total = s.get("total")
        if isinstance(total, int):
            out[sym] = total
            continue

        cats = s.get("categories") or {}
        t = 0
        if isinstance(cats, dict):
            for cat in cats.values():
                if not isinstance(cat, dict):
                    continue
                checks = cat.get("checks") or []
                if isinstance(checks, list):
                    for chk in checks:
                        if isinstance(chk, dict) and isinstance(chk.get("score"), int):
                            t += chk["score"]
        out[sym] = int(t)
    return out


def test_scoring_ranges_bullish_fixture():
    scenario = Path("tests/fixtures/scenarios/bullish/jerboa_cache")
    assert scenario.exists()

    tmp_home = Path(tempfile.mkdtemp())
    contract = _run_ui_export_from_fixture(tmp_home, scenario)

    sectors = contract.get("data", {}).get("sectors")
    assert isinstance(sectors, list)
    assert len(sectors) > 0

    for s in sectors:
        assert isinstance(s, dict)
        assert isinstance(s.get("symbol"), str)

        cats = s.get("categories")
        assert isinstance(cats, dict)
        assert cats, "expected categories"

        # Range checks: check scores are ints, totals are consistent
        for cat_k, cat in cats.items():
            assert isinstance(cat_k, str)
            assert isinstance(cat, dict)
            checks = cat.get("checks")
            assert isinstance(checks, list)
            assert 1 <= len(checks) <= 12  # matches MAX_PER_CATEGORY intent

            scores = []
            for chk in checks:
                assert isinstance(chk, dict)
                assert isinstance(chk.get("label"), str)
                sc = chk.get("score")
                assert isinstance(sc, int)
                assert sc >= 0  # scores are non-negative ints
                scores.append(sc)

            # If category total is present, it should match sum(scores)
            cat_total = cat.get("total")
            if isinstance(cat_total, int):
                assert cat_total == sum(scores)


def test_scoring_regression_snapshot_bullish_totals():
    expected_p = Path("tests/fixtures/expected/sector_totals.bullish.json")
    assert expected_p.exists(), (
        "run snapshot generator once to create sector_totals.bullish.json"
    )

    expected = json.loads(expected_p.read_text(encoding="utf-8"))
    assert isinstance(expected, dict)

    scenario = Path("tests/fixtures/scenarios/bullish/jerboa_cache")
    tmp_home = Path(tempfile.mkdtemp())
    contract = _run_ui_export_from_fixture(tmp_home, scenario)

    got = _sector_totals(contract)
    assert got == {k: int(v) for k, v in expected.items()}
