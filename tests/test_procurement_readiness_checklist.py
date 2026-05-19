from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_procurement_readiness_checklist_export
from max.exports.procurement_readiness_checklist import (
    render_procurement_readiness_checklist_json,
    render_procurement_readiness_checklist_markdown,
)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = metadata.get("title", unit_id)
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_procurement_statuses_and_blocked_items_are_deterministic() -> None:
    report = build_procurement_readiness_checklist_export(_store([
        _unit("ready", {"account": "Acme", "security_questionnaire_status": "approved", "legal_status": "complete", "dpa_status": "signed", "pricing_approval_status": "approved", "integration_requirements": "none", "data_residency_requirements": "not required"}),
        _unit("blocked", {"account": "Beta", "security_questionnaire_status": "blocked", "legal_status": "pending", "owner": "Sales Ops"}),
        _unit("unknown", {"account": "Core"}),
    ]))

    assert [row["idea_id"] for row in report["checklist_rows"]] == ["blocked", "unknown", "ready"]
    assert report["checklist_rows"][0]["readiness_status"] == "blocked"
    assert "security questionnaire" in report["checklist_rows"][0]["missing_items"]
    assert report["checklist_rows"][1]["readiness_status"] == "unknown"
    assert report["checklist_rows"][2]["readiness_status"] == "ready"
    assert report["summary"]["blocked_count"] == 1
    assert report["blocked_items"][0]["idea_id"] == "blocked"


def test_procurement_renderers_handle_empty_store() -> None:
    report = build_procurement_readiness_checklist_export(_store([]), domain="sales")

    assert json.loads(render_procurement_readiness_checklist_json(report))["checklist_rows"] == []
    markdown = render_procurement_readiness_checklist_markdown(report)
    assert "Procurement Readiness Checklist" in markdown
    assert "No procurement readiness metadata" in markdown
