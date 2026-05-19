from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports import build_integration_sla_compliance_report_export
from max.exports.integration_sla_compliance_report import (
    render_integration_sla_compliance_report_csv,
    render_integration_sla_compliance_report_json,
    render_integration_sla_compliance_report_markdown,
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


def test_integration_sla_statuses_sort_and_totals() -> None:
    report = build_integration_sla_compliance_report_export(_store([
        _unit("ok", {"integration_name": "Stripe", "uptime_percentage": 99.99, "sla_target": 99.9, "incident_count": 0, "p95_latency_ms": 250, "error_rate": 0.001}),
        _unit("warn", {"integration_name": "Slack", "uptime_percentage": 99.93, "sla_target": 99.9, "incident_count": 1, "p95_latency_ms": 1200, "error_rate": 0.01}),
        _unit("bad", {"integration_name": "Salesforce", "uptime_percentage": 99.4, "sla_target": 99.9, "breach_minutes": 45, "dependency_owner": "Platform"}),
        _unit("unknown", {"integration_name": "HubSpot"}),
    ]))

    assert [row["idea_id"] for row in report["integration_rows"]] == ["bad", "warn", "unknown", "ok"]
    assert report["integration_rows"][0]["compliance_status"] == "breached"
    assert report["summary"]["status_counts"]["warning"] == 1
    assert report["breach_totals"]["breach_minutes"] == 45


def test_integration_sla_renderers_handle_empty_store_and_csv_headers() -> None:
    report = build_integration_sla_compliance_report_export(_store([]), domain="platform")

    assert json.loads(render_integration_sla_compliance_report_json(report))["integration_rows"] == []
    markdown = render_integration_sla_compliance_report_markdown(report)
    assert "No integration SLA metadata" in markdown
    rows = list(csv.DictReader(io.StringIO(render_integration_sla_compliance_report_csv(report))))
    assert rows == []
    assert "integration_name,compliance_status" in render_integration_sla_compliance_report_csv(report)
