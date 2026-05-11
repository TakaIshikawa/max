"""Tests for integration dependency health exports."""

from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock

from max.exports.integration_dependency_health import (
    build_integration_dependency_health_export,
    render_integration_dependency_health_csv,
    render_integration_dependency_health_markdown,
)


def _unit(unit_id: str = "u1", title: str = "Checkout", metadata: dict | None = None) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = "platform"
    unit.metadata = metadata or {}
    return unit


def test_builds_rows_from_string_and_dict_integrations() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit(metadata={"integrations": ["stripe", {"provider": "sendgrid", "status": "degraded", "criticality": "high", "fallback_available": False}]}),
    ]

    report = build_integration_dependency_health_export(store, domain="platform")

    assert report["source"]["domain_filter"] == "platform"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="platform")
    rows = {row["provider"]: row for row in report["integrations"]}
    assert rows["stripe"]["risk_level"] == "medium"
    assert rows["sendgrid"]["status"] == "degraded"
    assert rows["sendgrid"]["risk_level"] == "high"


def test_flags_stale_sync_and_provider_rollup() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit(metadata={"integrations": [{"provider": "salesforce", "last_successful_sync": "2026-01-01T00:00:00Z", "fallback_available": True}]}),
    ]

    report = build_integration_dependency_health_export(store)

    row = report["integrations"][0]
    assert row["stale_sync"] is True
    assert row["status"] == "stale"
    assert row["risk_level"] == "medium"
    assert report["summary"]["by_provider"][0]["provider"] == "salesforce"


def test_markdown_and_csv_include_operational_fields() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit(metadata={"external_services": "github", "fallback_available": True})]
    report = build_integration_dependency_health_export(store)

    markdown = render_integration_dependency_health_markdown(report)
    rows = list(csv.DictReader(io.StringIO(render_integration_dependency_health_csv(report))))

    assert "# Integration Dependency Health" in markdown
    assert "Recommended Action" in markdown
    assert rows[0]["provider"] == "github"
    assert rows[0]["recommended_action"] == "Continue monitoring"
