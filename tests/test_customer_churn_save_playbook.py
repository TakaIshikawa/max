from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_customer_churn_save_playbook_export
from max.exports.customer_churn_save_playbook import (
    render_customer_churn_save_playbook_json,
    render_customer_churn_save_playbook_markdown,
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


def test_churn_save_playbook_orders_risk_and_builds_actions() -> None:
    report = build_customer_churn_save_playbook_export(_store([
        _unit("low", {"account": "Acme", "account_health": 92, "renewal_date": "2026-12-01", "owner": "CSM"}),
        _unit("critical", {"account": "Beta", "account_health": 20, "adoption_gaps": ["low admin usage"], "blockers": ["pricing objection"], "renewal_date": "2026-06-01"}),
    ]))

    assert [row["idea_id"] for row in report["playbook_rows"]] == ["critical", "low"]
    assert report["playbook_rows"][0]["churn_risk"] == "critical"
    assert "pricing objection" in report["playbook_rows"][0]["churn_drivers"]
    assert report["playbook_rows"][0]["intervention_actions"][0] == "Resolve blocker: pricing objection"
    assert report["summary"]["blocked_account_count"] == 1
    assert report["escalation_criteria"]


def test_churn_save_playbook_handles_empty_optional_fields() -> None:
    report = build_customer_churn_save_playbook_export(_store([_unit("empty", {})]), domain="success")
    row = report["playbook_rows"][0]

    assert row["account_context"]["account"] == "Unknown"
    assert row["owner_assignment"]["owner"] == "Unassigned"
    assert row["adoption_gaps"] == []
    assert row["intervention_timing"] == "next account review"
    assert report["source"]["domain_filter"] == "success"


def test_churn_save_playbook_renderers_are_json_serializable() -> None:
    report = build_customer_churn_save_playbook_export(_store([]))

    assert json.loads(render_customer_churn_save_playbook_json(report))["playbook_rows"] == []
    markdown = render_customer_churn_save_playbook_markdown(report)
    assert "Customer Churn-Save Playbook" in markdown
    assert "No customer churn-save metadata" in markdown
