import json
from pathlib import Path


def test_issue167_calibration_artifact_is_consistent_with_issue166_inputs():
    cal_p = Path("tests/fixtures/allocator_calibration_issue167.v1.json")
    scen_p = Path("tests/fixtures/allocator_scenarios_issue166.v1.json")

    cal = json.loads(cal_p.read_text(encoding="utf-8"))
    scen = json.loads(scen_p.read_text(encoding="utf-8"))

    assert cal["schema"] == "allocator_calibration_issue167.v1"
    assert scen["schema"] == "allocator_scenarios_issue166.v1"

    assert cal["comparison_inputs_from"] == str(scen_p)

    defaults = cal["recommended_defaults"]
    assert defaults["min_floor"] == 0.55
    assert defaults["min_delta"] == 0.12

    scenario_names = {s["name"] for s in scen["scenarios"]}
    expected_names = {s["name"] for s in cal["scenario_expectations"]}
    assert expected_names == scenario_names

    modes = {m["name"] for m in cal["modes"]}
    assert modes == {"sgov-only", "sgov-plus-metals"}

    recommendation = cal["recommendation"]
    assert recommendation["keep_defaults"] is True
    assert recommendation["follow_up_needed"] is False
    assert len(recommendation["justification"]) >= 3
