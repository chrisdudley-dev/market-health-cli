from datetime import date

from market_health.calibration_v1 import build_calibration_v1, validate_calibration_v1


def test_calibration_v1_default_doc_valid():
    doc = build_calibration_v1(asof_date=date(2026, 1, 1))
    errors = validate_calibration_v1(doc)
    assert errors == []


def test_calibration_v1_overrides_valid():
    doc = build_calibration_v1(
        asof_date=date(2026, 1, 1),
        thresholds={"min_improvement_threshold": 0.2, "disagreement_veto_edge": 0.1},
        constraints={
            "max_weight_per_symbol": 0.2,
            "min_distinct_symbols": 6,
            "hhi_cap": 0.2,
        },
        notes="test",
    )
    errors = validate_calibration_v1(doc)
    assert errors == []
