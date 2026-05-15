from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_pricing_discount_leakage_report_export
from max.exports.pricing_discount_leakage_report import render_pricing_discount_leakage_report_markdown


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = unit_id
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_aggregates_segments_and_estimated_impact() -> None:
    report = build_pricing_discount_leakage_report_export(_store([
        _unit("a", {"segment": "enterprise", "list_price_usd": 100_000, "actual_price_usd": 70_000, "evidence_references": ["contract"]}),
        _unit("b", {"segment": "enterprise", "arr_usd": 50_000, "discount_rate": 0.1}),
    ]))

    segment = report["leakage_segments"][0]
    assert segment["segment"] == "enterprise"
    assert segment["estimated_impact_usd"] == 35_000
    assert segment["evidence_count"] == 2
    assert report["summary"]["total_estimated_impact_usd"] == 35_000


def test_thresholds_classify_low_medium_and_high_deterministically() -> None:
    report = build_pricing_discount_leakage_report_export(_store([
        _unit("low", {"arr_usd": 100_000, "discount_rate": 0.05}),
        _unit("medium", {"arr_usd": 100_000, "discount_rate": 0.15}),
        _unit("high", {"arr_usd": 100_000, "discount_rate": 0.3}),
    ]))

    assert [row["idea_id"] for row in report["deal_rows"]] == ["high", "medium", "low"]
    assert [row["leakage_level"] for row in report["deal_rows"]] == ["high", "medium", "low"]
    assert "Pricing Discount Leakage Report" in render_pricing_discount_leakage_report_markdown(report)
