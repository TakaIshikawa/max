from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_incident_comms_matrix as exported_generate
from max.spec import render_incident_comms_matrix_csv as exported_render_csv
from max.spec import render_incident_comms_matrix_markdown as exported_render_markdown
from max.spec.incident_comms_matrix import (
    INCIDENT_COMMS_MATRIX_CSV_COLUMNS,
    INCIDENT_COMMS_MATRIX_SCHEMA_VERSION,
    generate_incident_comms_matrix,
    render_incident_comms_matrix_csv,
    render_incident_comms_matrix_markdown,
)


def test_generate_incident_comms_matrix_uses_launch_context() -> None:
    matrix = generate_incident_comms_matrix(_tact_spec())

    assert matrix["schema_version"] == INCIDENT_COMMS_MATRIX_SCHEMA_VERSION
    assert matrix["kind"] == "max.incident_comms_matrix"
    assert matrix["source"]["idea_id"] == "bu-incident-comms"
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
    assert matrix["summary"]["buyer"] == "support operations director"
    assert matrix["summary"]["target_user"] == "support operator"
    assert matrix["summary"]["workflow_context"] == "customer escalation workflow with Slack support handoff"
    assert any(row["stakeholder"] == "support operations director" for row in matrix["stakeholder_channels"])
    assert any("support queue triage" in row["description"] for row in matrix["stakeholder_channels"])


def test_incident_comms_markdown_groups_by_severity_and_channel() -> None:
    matrix = generate_incident_comms_matrix(_tact_spec())
    markdown = render_incident_comms_matrix_markdown(matrix)

    assert markdown == render_incident_comms_matrix_markdown(matrix)
    assert markdown.startswith("# Escalation Signal Router Incident Communications Matrix")
    assert "## Severity Notifications" in markdown
    assert "### SEV1" in markdown
    assert "### SEV2" in markdown
    assert "### SEV3" in markdown
    assert "## Stakeholder Channels" in markdown
    assert "### support operations director" in markdown
    assert "## Status Promises" in markdown


def test_incident_comms_csv_has_stable_columns_and_ordering() -> None:
    matrix = generate_incident_comms_matrix(_tact_spec())
    csv_text = render_incident_comms_matrix_csv(matrix)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_incident_comms_matrix_csv(matrix)
    assert csv_text.splitlines()[0] == ",".join(INCIDENT_COMMS_MATRIX_CSV_COLUMNS)
    assert [row["section"] for row in rows[:4]] == ["stakeholder_channels"] * 4
    assert rows[0]["item_id"] == "SC1"
    assert rows[0]["stakeholder"] == "support operations director"
    assert rows[4]["section"] == "severity_notifications"


def test_incident_comms_exported_functions() -> None:
    matrix = exported_generate(_tact_spec())

    assert exported_render_markdown(matrix).startswith("# Escalation Signal Router")
    assert exported_render_csv(matrix).startswith(",".join(INCIDENT_COMMS_MATRIX_CSV_COLUMNS))


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-incident-comms", "status": "approved", "domain": "support"},
        "project": {
            "title": "Escalation Signal Router",
            "summary": "Route customer escalation signals to support owners.",
            "target_users": "support teams",
            "specific_user": "support operator",
            "buyer": "support operations director",
            "workflow_context": "customer escalation workflow with Slack support handoff",
            "support_context": "support queue triage and customer follow-up",
        },
        "solution": {
            "technical_approach": "FastAPI API posts Slack alerts and writes escalation audit logs.",
            "suggested_stack": {"backend": "FastAPI", "messaging": "Slack", "database": "Postgres"},
        },
        "execution": {
            "validation_plan": "Run incident drill and support response review.",
            "risks": ["Slack outage may delay customer escalation updates."],
        },
        "evidence": {"insight_ids": ["ins-1"], "rationale": "Support needs consistent incident updates."},
    }
