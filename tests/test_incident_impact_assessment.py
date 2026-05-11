"""Tests for incident impact assessment exports."""

from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock

from max.exports.incident_impact_assessment import build_incident_impact_assessment_export, render_incident_impact_assessment_csv, render_incident_impact_assessment_markdown


def _unit(unit_id: str, metadata: dict | None = None) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = f"Unit {unit_id}"
    unit.metadata = metadata or {}
    return unit


def test_builds_incident_rows_gaps_and_aggregates() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit("a", {"severity": "sev1", "affected_customers": 2500, "revenue_at_risk": 300000, "downtime_minutes": 90, "owner": "ops", "dependencies": ["db"], "mitigation_status": "open"}),
        _unit("b", {"severity": "sev3", "affected_customers": 10}),
    ]

    report = build_incident_impact_assessment_export(store, domain="platform")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="platform")
    assert report["incident_rows"][0]["recovery_priority"] == "critical"
    assert report["incident_rows"][0]["mitigation_gaps"] == ["unresolved_mitigation"]
    assert set(report["incident_rows"][1]["mitigation_gaps"]) == {"missing_owner", "missing_dependencies", "unresolved_mitigation"}
    assert report["summary"]["total_revenue_at_risk"] == 300000
    assert report["summary"]["total_affected_customers"] == 2510


def test_renderers_include_expected_fields() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit("a", {"severity": "sev2", "owner": "ops", "dependencies": ["api"], "mitigation_status": "resolved"})]
    report = build_incident_impact_assessment_export(store)

    markdown = render_incident_impact_assessment_markdown(report)
    rows = list(csv.DictReader(io.StringIO(render_incident_impact_assessment_csv(report))))

    assert "# Incident Impact Assessment" in markdown
    assert "## Owner Rollup" in markdown
    assert rows[0]["severity"] == "sev2"
