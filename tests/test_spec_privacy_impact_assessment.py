from __future__ import annotations

import json

from max.spec import generate_privacy_impact_assessment as exported_generate
from max.spec import render_privacy_impact_assessment_markdown as exported_render
from max.spec.privacy_impact_assessment import (
    PRIVACY_IMPACT_ASSESSMENT_SCHEMA_VERSION,
    generate_privacy_impact_assessment,
    render_privacy_impact_assessment_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-privacy",
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
                "OpenAI summaries, Slack alerts, and encrypted credential handling."
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
        "evidence": {"insight_ids": ["ins-privacy"], "signal_ids": ["sig-privacy"]},
    }


def test_generate_privacy_impact_assessment_is_deterministic_and_json_ready() -> None:
    first = generate_privacy_impact_assessment(_rich_tact_spec())
    second = generate_privacy_impact_assessment(_rich_tact_spec())

    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["schema_version"] == PRIVACY_IMPACT_ASSESSMENT_SCHEMA_VERSION
    assert first["kind"] == "max.spec.privacy_impact_assessment"
    assert first["source"]["idea_id"] == "bu-privacy"
    assert first["summary"]["title"] == "Patient Follow-Up Automation"
    assert first["summary"]["privacy_gate"] == "privacy_review_required"
    assert first["summary"]["privacy_sensitive_input_status"] == "detected"
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "privacy_context",
        "data_subjects",
        "personal_data",
        "processing_purposes",
        "risks",
        "mitigations",
        "review_actions",
    }

    subject_ids = {item["id"] for item in first["data_subjects"]}
    data_ids = {item["id"] for item in first["personal_data"]}
    assert "patient" in subject_ids
    assert "operator" in subject_ids
    assert "identifiers" in data_ids
    assert "regulated_sensitive_data" in data_ids
    assert "authentication_data" in data_ids
    assert any(item["category"] == "third_party_transfer" for item in first["risks"])
    assert any("solution.suggested_stack" in item["evidence"] for item in first["risks"])
    assert first["privacy_context"]["evidence_refs"] == [
        "insight:ins-privacy",
        "signal:sig-privacy",
    ]


def test_sparse_specs_render_empty_state_for_missing_privacy_sensitive_inputs() -> None:
    assessment = generate_privacy_impact_assessment(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-privacy"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
        }
    )
    markdown = render_privacy_impact_assessment_markdown(assessment)

    assert assessment["summary"]["title"] == "bu-sparse-privacy"
    assert assessment["summary"]["workflow_context"] == "primary workflow"
    assert assessment["summary"]["privacy_gate"] == "field_inventory_required"
    assert assessment["summary"]["privacy_sensitive_input_status"] == "not_detected"
    assert assessment["data_subjects"][0]["id"] == "target_user"
    assert assessment["personal_data"] == []
    assert any(item["category"] == "field_inventory_gap" for item in assessment["risks"])
    assert "No privacy-sensitive inputs were detected in the spec" in markdown
    assert "## Review Actions" in markdown


def test_render_privacy_impact_assessment_markdown_has_stable_sections() -> None:
    assessment = generate_privacy_impact_assessment(_rich_tact_spec())

    first = render_privacy_impact_assessment_markdown(assessment)
    second = render_privacy_impact_assessment_markdown(assessment)

    assert first == second
    assert first.startswith("# Patient Follow-Up Automation Privacy Impact Assessment")
    assert f"- Schema version: {PRIVACY_IMPACT_ASSESSMENT_SCHEMA_VERSION}" in first
    for heading in [
        "## Data Subjects",
        "## Personal Data",
        "## Processing Purposes",
        "## Privacy Risks",
        "## Mitigations",
        "## Review Actions",
    ]:
        assert heading in first
    assert "regulated_sensitive_data" in first
    assert "Patient data retention and deletion rules may block launch" in first
    assert "PIA-M" in first


def test_privacy_impact_assessment_is_importable_from_spec_package() -> None:
    assessment = exported_generate(_rich_tact_spec())
    markdown = exported_render(assessment)

    assert assessment["schema_version"] == PRIVACY_IMPACT_ASSESSMENT_SCHEMA_VERSION
    assert markdown.startswith("# Patient Follow-Up Automation Privacy Impact Assessment")
