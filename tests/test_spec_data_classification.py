from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec import generate_data_classification as exported_generate
from max.spec import render_data_classification_csv as exported_render_csv
from max.spec import render_data_classification_markdown as exported_render_markdown
from max.spec.data_classification import (
    DATA_CLASSIFICATION_CSV_COLUMNS,
    DATA_CLASSIFICATION_SCHEMA_VERSION,
    generate_data_classification,
    render_data_classification_csv,
    render_data_classification_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-data",
            "status": "approved",
            "domain": "healthcare",
            "category": "automation",
        },
        "project": {
            "title": "Patient Follow-Up Automation",
            "summary": "Coordinate patient follow-up after intake.",
            "target_users": "clinic operations teams",
            "specific_user": "clinic coordinator",
            "buyer": "clinic operations director",
            "workflow_context": "patient intake to follow-up queue",
        },
        "problem": {
            "statement": "Teams copy patient emails and PII into spreadsheets.",
            "current_workaround": "Manual exports from Salesforce into Slack with patient account notes.",
            "why_now": "HIPAA review is needed before production OAuth access.",
        },
        "solution": {
            "approach": "Sync patient follow-up records and generate AI summaries.",
            "technical_approach": (
                "FastAPI webhook service with Postgres storage, OAuth tokens, audit logs, "
                "OpenAI summaries, Slack alerts, and encrypted secret handling."
            ),
            "suggested_stack": {
                "backend": "FastAPI",
                "database": "Postgres",
                "ai": "OpenAI",
                "messaging": "Slack",
                "crm": "Salesforce",
                "auth": "OAuth",
            },
        },
        "execution": {
            "mvp_scope": [
                "Patient follow-up queue",
                "Slack reminder export",
                "Admin audit log review",
            ],
            "validation_plan": "Use de-identified fixtures and delete test data after validation.",
            "risks": [
                "Patient data retention and deletion rules may block launch.",
                "Slack notifications could expose PII.",
            ],
        },
    }


def test_generate_data_classification_is_deterministic_and_json_ready() -> None:
    first = generate_data_classification(_rich_tact_spec())
    second = generate_data_classification(_rich_tact_spec())

    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["schema_version"] == DATA_CLASSIFICATION_SCHEMA_VERSION
    assert first["kind"] == "max.spec.data_classification"
    assert first["source"]["idea_id"] == "bu-data"
    assert first["summary"]["title"] == "Patient Follow-Up Automation"
    assert first["summary"]["sensitivity_level"] == "restricted"
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "classification_context",
        "data_categories",
        "sensitivity",
        "retention_guidance",
        "compliance_considerations",
        "storage_touchpoints",
        "transfer_touchpoints",
        "risk_notes",
        "implementation_safeguards",
    }

    by_id = {item["id"]: item for item in first["data_categories"]}
    assert by_id["personal_identifiers"]["sensitivity"] == "confidential"
    assert by_id["regulated_personal_data"]["sensitivity"] == "restricted"
    assert by_id["authentication_and_secrets"]["sensitivity"] == "restricted"
    assert by_id["ai_inputs_and_outputs"]["label"] == "AI inputs and outputs"
    assert first["classification_context"]["regulated_domain"] is True
    assert first["storage_touchpoints"][0]["id"] == "STORE01"
    assert any(item["name"] == "Postgres" for item in first["storage_touchpoints"])
    assert any(item["name"] == "Slack" for item in first["transfer_touchpoints"])
    assert any(item["id"].startswith("DATA-SG") for item in first["implementation_safeguards"])


def test_sparse_specs_produce_conservative_fallback_classification() -> None:
    classification = generate_data_classification(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-data"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
        }
    )

    assert classification["summary"]["title"] == "bu-sparse-data"
    assert classification["summary"]["workflow_context"] == "primary workflow"
    assert classification["summary"]["sensitivity_level"] == "confidential"
    assert classification["data_categories"] == [
        {
            "id": "unspecified_user_or_operational_data",
            "label": "Unspecified user or operational data",
            "sensitivity": "confidential",
            "description": "Sparse specs do not prove that the system avoids user, workflow, or operational data.",
            "evidence": ["project", "problem", "solution"],
            "handling_notes": (
                "Treat all persisted records and logs as confidential until the implementation names exact fields."
            ),
        }
    ]
    assert classification["storage_touchpoints"][0]["name"] == "Persistence boundary"
    assert "Sparse input means data minimization" in classification["risk_notes"][0]
    assert classification["implementation_safeguards"]


def test_render_data_classification_markdown_has_stable_sections() -> None:
    classification = generate_data_classification(_rich_tact_spec())

    first = render_data_classification_markdown(classification)
    second = render_data_classification_markdown(classification)

    assert first == second
    assert first.startswith("# Patient Follow-Up Automation Data Classification")
    assert f"- Schema version: {DATA_CLASSIFICATION_SCHEMA_VERSION}" in first
    assert "## Data Categories" in first
    assert "## Retention Guidance" in first
    assert "## Risk Notes" in first
    assert "## Safeguards" in first
    assert "regulated_personal_data" in first
    assert "Patient data retention and deletion rules may block launch" in first
    assert "Default retention" in first
    assert "DATA-SG" in first


def test_render_data_classification_csv_has_stable_header_and_rows() -> None:
    classification = generate_data_classification(_rich_tact_spec())

    first = render_data_classification_csv(classification)
    second = render_data_classification_csv(classification)
    rows = list(csv.DictReader(StringIO(first)))

    assert first == second
    assert first.startswith(",".join(DATA_CLASSIFICATION_CSV_COLUMNS) + "\n")
    assert list(rows[0]) == list(DATA_CLASSIFICATION_CSV_COLUMNS)
    assert [row["section"] for row in rows[:5]] == [
        "summary",
        "data_categories",
        "data_categories",
        "data_categories",
        "data_categories",
    ]
    assert [row["item_id"] for row in rows if row["section"] == "data_categories"] == [
        item["id"] for item in classification["data_categories"]
    ]


def test_render_data_classification_csv_covers_levels_controls_and_evidence() -> None:
    classification = generate_data_classification(_rich_tact_spec())
    rows = list(csv.DictReader(StringIO(render_data_classification_csv(classification))))

    categories = {
        row["item_id"]: row for row in rows if row["row_type"] == "data_category"
    }
    assert categories["personal_identifiers"]["sensitivity"] == "confidential"
    assert categories["personal_identifiers"]["evidence"] == "email; PII"
    assert categories["regulated_personal_data"]["sensitivity"] == "restricted"
    assert categories["regulated_personal_data"]["evidence"] == "patient; HIPAA; health"
    assert categories["authentication_and_secrets"]["handling_requirement"] == (
        "Store in secret-managed locations only; redact from logs and exports."
    )

    control_rows = [row for row in rows if row["row_type"] == "control"]
    assert {row["owner"] for row in control_rows} >= {"data_owner", "security_owner"}
    assert all(row["control"].startswith("DATA-SG") for row in control_rows)
    assert any(
        row["row_type"] == "handling_requirement"
        and row["section"] == "retention_guidance"
        and row["item_id"] == "default_retention"
        for row in rows
    )
    assert any(
        row["section"] == "transfer_touchpoints" and row["item_name"] == "Slack"
        for row in rows
    )


def test_data_classification_is_importable_from_spec_package() -> None:
    classification = exported_generate(_rich_tact_spec())
    markdown = exported_render_markdown(classification)
    csv_text = exported_render_csv(classification)

    assert classification["schema_version"] == DATA_CLASSIFICATION_SCHEMA_VERSION
    assert markdown.startswith("# Patient Follow-Up Automation Data Classification")
    assert csv_text.startswith(",".join(DATA_CLASSIFICATION_CSV_COLUMNS) + "\n")
