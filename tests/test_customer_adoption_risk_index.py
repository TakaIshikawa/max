"""Tests for customer adoption risk index exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import (
    build_customer_adoption_risk_index_export as exported_build,
    render_customer_adoption_risk_index_json as exported_render_json,
)
from max.exports.customer_adoption_risk_index import (
    KIND,
    SCHEMA_VERSION,
    build_customer_adoption_risk_index_export,
    render_customer_adoption_risk_index_json,
    render_customer_adoption_risk_index_markdown,
)


def test_customer_adoption_risk_index_scores_rows_and_summary() -> None:
    store = _store([
        _unit("high", "High Adoption Risk"),
        _unit("low", "Low Adoption Risk", specific_user="ops lead", buyer="VP Ops", workflow_context="weekly review", validation_plan="pilot", evidence_signals=["sig"], current_workaround="spreadsheet", domain_risks=[]),
    ])

    report = build_customer_adoption_risk_index_export(store, domain="ops")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"]["domain_filter"] == "ops"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="ops")
    assert [row["idea_id"] for row in report["risk_rows"]] == ["high", "low"]
    assert report["risk_rows"][0]["severity"] == "high"
    assert report["risk_rows"][0]["risk_drivers"][:3] == [
        "Target user clarity",
        "Workflow specificity",
        "Buyer strength",
    ]
    assert report["summary"]["idea_count"] == 2
    assert report["summary"]["severity_counts"]["high"] == 1


def test_customer_adoption_risk_index_renderers_and_exports() -> None:
    report = exported_build(_store([_unit("idea", "Adoption Idea")]))
    markdown = render_customer_adoption_risk_index_markdown(report)
    rendered_json = exported_render_json(report)

    assert "# Customer Adoption Risk Index" in markdown
    assert "## Risk Rows" in markdown
    assert json.loads(render_customer_adoption_risk_index_json(report))["kind"] == KIND
    assert json.loads(rendered_json)["risk_rows"][0]["idea_id"] == "idea"


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def _unit(unit_id: str, title: str, **values) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = values.pop("metadata", {})
    defaults = {
        "specific_user": "",
        "buyer": "",
        "workflow_context": "",
        "validation_plan": "",
        "evidence_signals": [],
        "inspiring_insights": [],
        "current_workaround": "manual migration",
        "composability_notes": "",
        "value_proposition": "",
        "domain_risks": ["support owner unclear"],
    }
    defaults.update(values)
    for key, value in defaults.items():
        setattr(unit, key, value)
    return unit
