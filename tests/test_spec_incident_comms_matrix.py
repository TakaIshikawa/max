"""Tests for TactSpec incident communications matrix generation."""

from __future__ import annotations

import csv
import io

from max.spec import generate_incident_comms_matrix, render_incident_comms_matrix_csv, render_incident_comms_matrix_markdown
from max.spec.generator import generate_spec_preview
from max.spec.incident_comms_matrix import INCIDENT_COMMS_MATRIX_CSV_COLUMNS


def test_incident_comms_matrix_shape_and_contextual_channels(sample_unit, sample_evaluation) -> None:
    matrix = generate_incident_comms_matrix(generate_spec_preview(sample_unit, sample_evaluation))

    assert matrix["kind"] == "max.incident_comms_matrix"
    assert set(matrix) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "stakeholder_channels",
        "severity_notifications",
        "message_templates",
        "escalation_handoffs",
        "status_promises",
        "evidence_references",
    }
    assert "MCP server maintainer" in matrix["stakeholder_channels"][0]["description"]
    assert "developer platform lead" in matrix["stakeholder_channels"][1]["description"]


def test_incident_comms_matrix_renderers_group_severity_and_channels(sample_unit, sample_evaluation) -> None:
    matrix = generate_incident_comms_matrix(generate_spec_preview(sample_unit, sample_evaluation))
    markdown = render_incident_comms_matrix_markdown(matrix)
    csv_text = render_incident_comms_matrix_csv(matrix)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert "# MCP Test Framework Incident Communications Matrix" in markdown
    assert markdown.index("## Severity Notifications") < markdown.index("## Stakeholder Channels")
    assert csv_text.splitlines()[0] == ",".join(INCIDENT_COMMS_MATRIX_CSV_COLUMNS)
    assert any(row["section"] == "status_promises" and row["name"] == "customer_update_cadence" for row in rows)
