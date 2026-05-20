from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.implementation_scope_drift_report import (
    build_implementation_scope_drift_report_export,
    render_implementation_scope_drift_report_json,
    render_implementation_scope_drift_report_markdown,
)


def _unit(unit_id: str, title: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_scope_drift_severity_approval_gaps_and_sorting() -> None:
    report = build_implementation_scope_drift_report_export(
        _store(
            [
                _unit("low", "Stable", {"account": "Zenith", "approval_status": "approved"}),
                _unit("medium", "Moderate", {"account": "Acme", "added_requirements": ["SSO"], "timeline_impact_days": 5, "approval_status": "approved"}),
                _unit("high", "Major", {"account": "Beta", "added_requirements": ["SSO", "SCIM"], "change_requests": ["New region"], "timeline_impact_days": 14, "budget_impact": "12000", "approval_status": "pending"}),
            ]
        )
    )

    assert [row["idea_id"] for row in report["drift_rows"]] == ["high", "medium", "low"]
    assert report["drift_rows"][0]["drift_severity"] == "high"
    assert report["drift_rows"][0]["approval_gap"] is True
    assert report["summary"]["severity_counts"] == {"high": 1, "medium": 1, "low": 1}
    assert report["approval_gaps"][0]["idea_id"] == "high"


def test_domain_forwarding_renderers_and_empty_state() -> None:
    store = _store([])
    report = build_implementation_scope_drift_report_export(store, domain="enterprise")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")
    assert report["source"]["domain_filter"] == "enterprise"
    assert json.loads(render_implementation_scope_drift_report_json(report)) == report
    assert "No implementation scope records found" in render_implementation_scope_drift_report_markdown(report)
