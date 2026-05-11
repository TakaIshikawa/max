from __future__ import annotations

import csv
from io import StringIO
from unittest.mock import MagicMock

from max.exports.integration_readiness_matrix import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_integration_readiness_matrix_export,
    render_integration_readiness_matrix_csv,
    render_integration_readiness_matrix_json,
    render_integration_readiness_matrix_markdown,
)


def test_integration_readiness_matrix_detects_missing_artifacts() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit("idea-1", "Slack Sync", {"integrations": ["Slack", "Salesforce"], "credentials": ["Slack token"], "contracts": ["Slack contract"], "integration_tests": ["Slack test"], "integration_owner": "platform owner"})
    ]

    report = build_integration_readiness_matrix_export(store, domain="sales")
    rows = list(csv.DictReader(StringIO(render_integration_readiness_matrix_csv(report))))

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"]["domain_filter"] == "sales"
    assert len(report["integration_rows"]) == 2
    assert report["integration_rows"][0]["readiness"] == "blocked"
    assert report["integration_rows"][0]["missing_artifacts"]
    assert report["integration_rows"][0]["recommended_action"]
    assert render_integration_readiness_matrix_csv(report).splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0]["idea_id"] == "idea-1"
    assert "Integration Readiness Matrix" in render_integration_readiness_matrix_markdown(report)
    assert '"integration_rows"' in render_integration_readiness_matrix_json(report)
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="sales")


def _unit(unit_id: str, title: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata
    return unit
