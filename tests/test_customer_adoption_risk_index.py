from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.customer_adoption_risk_index import (
    KIND,
    SCHEMA_VERSION,
    build_customer_adoption_risk_index_export,
    render_customer_adoption_risk_index_json,
    render_customer_adoption_risk_index_markdown,
)


def test_customer_adoption_risk_index_scores_and_renders() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit("high", "High Adoption Risk", {"target_users": "", "workflow_context": "", "buyer": "", "support_readiness": "missing", "onboarding_complexity": "high", "pricing_friction": "high"}),
        _unit("low", "Low Adoption Risk", {"target_users": "support teams", "workflow_context": "case triage workflow", "buyer": "support VP", "validation_plan": "pilot done", "support_readiness": "ready", "onboarding_complexity": "low", "pricing_friction": "low"}),
    ]

    report = build_customer_adoption_risk_index_export(store, domain="support")
    markdown = render_customer_adoption_risk_index_markdown(report)
    parsed = json.loads(render_customer_adoption_risk_index_json(report))

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["risk_rows"][0]["idea_id"] == "high"
    assert report["risk_rows"][0]["severity"] == "high"
    assert report["risk_rows"][0]["dimension_scores"]
    assert report["risk_rows"][0]["risk_drivers"]
    assert report["risk_rows"][0]["recommended_mitigation"]
    assert report["summary"]["idea_count"] == 2
    assert "Customer Adoption Risk Index" in markdown
    assert parsed["source"]["domain_filter"] == "support"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="support")


def _unit(unit_id: str, title: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata
    return unit
