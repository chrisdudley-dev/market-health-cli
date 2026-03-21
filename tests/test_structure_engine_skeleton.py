from market_health.structure_engine import (
    StructureSummary,
    StructureZone,
    compute_structure_summary,
)


def test_structure_summary_defaults_are_stable() -> None:
    summary = compute_structure_summary("XLE", price=100.0)
    assert isinstance(summary, StructureSummary)
    assert summary.symbol == "XLE"
    assert summary.price == 100.0
    assert summary.version == "v1"
    assert isinstance(summary.nearest_support_zone, StructureZone)
    assert isinstance(summary.nearest_resistance_zone, StructureZone)


def test_structure_summary_to_dict_shape() -> None:
    summary = compute_structure_summary("XLK", price=200.0).to_dict()
    assert summary["symbol"] == "XLK"
    assert summary["price"] == 200.0
    assert "nearest_support_zone" in summary
    assert "nearest_resistance_zone" in summary
    assert "state_tags" in summary
