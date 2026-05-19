from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_customer_escalation_risk_report_export
from max.exports.customer_escalation_risk_report import (
    SCHEMA_VERSION,
    render_customer_escalation_risk_report_json,
    render_customer_escalation_risk_report_markdown,
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


def test_escalation_risk_rows_sort_highest_risk_first() -> None:
    report = build_customer_escalation_risk_report_export(_store([
        _unit("b", {"account": "Beta", "escalation_count": 2, "open_blockers": ["legal"], "severity": "high", "executive_sponsor_status": "active", "account_tier": "premium", "mitigation_owner": "CS"}),
        _unit("a", {"account": "Acme", "escalation_count": 4, "open_blockers": ["security", "pricing"], "severity": "sev1", "executive_sponsor_status": "missing", "renewal_date": "2026-06-01", "account_tier": "enterprise", "mitigation_owner": "VP Success"}),
        _unit("c", {"account": "Core", "escalation_count": 0, "executive_sponsor_status": "engaged"}),
    ]))

    assert report["schema_version"] == SCHEMA_VERSION
    assert [row["idea_id"] for row in report["escalation_rows"]] == ["a", "b", "c"]
    assert report["escalation_rows"][0]["risk_tier"] == "critical"
    assert report["summary"]["tier_counts"]["critical"] == 1
    assert report["risk_tiers"][0] == {"tier": "critical", "count": 1}
    assert "executive escalation review" in report["recommendations"][0]


def test_escalation_json_and_markdown_handle_empty_store() -> None:
    report = build_customer_escalation_risk_report_export(_store([]), domain="enterprise")

    assert report["summary"]["account_count"] == 0
    assert json.loads(render_customer_escalation_risk_report_json(report))["source"]["domain_filter"] == "enterprise"
    markdown = render_customer_escalation_risk_report_markdown(report)
    assert "Customer Escalation Risk Report" in markdown
    assert "No customer escalation metadata" in markdown
