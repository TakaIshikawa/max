from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.pricing_packaging_gap import build_pricing_packaging_gap_export, render_pricing_packaging_gap_csv, render_pricing_packaging_gap_json, render_pricing_packaging_gap_markdown


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = unit_id
    unit.domain = "growth"
    unit.metadata = metadata
    return unit


def test_pricing_packaging_gap_types_and_renderers() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit("under", {"plan_tier": "free", "feature_value_score": 90, "usage_count": 100, "request_count": 20, "revenue_impact": 50000}), _unit("parity", {"plan_tier": "enterprise", "feature_value_score": 80, "competitor_included_tier": "free"}), _unit("over", {"plan_tier": "enterprise", "feature_value_score": 20, "usage_count": 1}), _unit("weak", {})]
    report = build_pricing_packaging_gap_export(store, domain="growth")
    assert [row["gap_type"] for row in report["gaps"]] == ["under_monetized", "parity_risk", "over_packaged", "insufficient_signal"]
    assert report["summary"]["type_counts"]["under_monetized"] == 1
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="growth")
    assert render_pricing_packaging_gap_csv(report).splitlines()[0].startswith("idea_id,title")
    assert "## Tier Rollup" in render_pricing_packaging_gap_markdown(report)
    assert json.loads(render_pricing_packaging_gap_json(report))["kind"] == "max.pricing_packaging_gap"


def test_pricing_packaging_empty_report() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = []
    report = build_pricing_packaging_gap_export(store)
    assert report["gaps"] == []
    assert "Add pricing and packaging metadata" in report["recommendations"][0]
