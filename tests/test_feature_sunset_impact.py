from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.feature_sunset_impact import build_feature_sunset_impact_export, render_feature_sunset_impact_csv, render_feature_sunset_impact_json, render_feature_sunset_impact_markdown


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = metadata.get("feature_name", unit_id)
    unit.domain = "product"
    unit.metadata = metadata
    return unit


def test_feature_sunset_scores_impact_and_renders() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit("a", {"feature_name": "Legacy API", "active_user_count": 5000, "revenue_at_risk": 200000, "dependent_accounts": ["Acme", "Beta"], "migration_status": "not_started", "compliance_dependency": True}), _unit("b", {"feature_name": "Old Theme", "active_user_count": 5, "migration_status": "complete"})]
    report = build_feature_sunset_impact_export(store, domain="product")
    assert report["features"][0]["impact_band"] == "severe"
    assert report["summary"]["band_counts"]["severe"] == 1
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="product")
    assert render_feature_sunset_impact_csv(report).splitlines()[0].startswith("idea_id,feature_name")
    assert "## Impact Table" in render_feature_sunset_impact_markdown(report)
    assert json.loads(render_feature_sunset_impact_json(report))["schema_version"].endswith(".v1")


def test_feature_sunset_empty_report() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = []
    report = build_feature_sunset_impact_export(store)
    assert report["features"] == []
    assert "Add feature sunset metadata" in report["recommendations"][0]
