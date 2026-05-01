from __future__ import annotations

import json

from max.spec import generate_compliance_checklist as exported_generate
from max.spec import render_compliance_checklist_json as exported_render_json
from max.spec import render_compliance_checklist_markdown as exported_render_markdown
from max.spec.compliance_checklist import (
    COMPLIANCE_CHECKLIST_SCHEMA_VERSION,
    generate_compliance_checklist,
    render_compliance_checklist_json,
    render_compliance_checklist_markdown,
)


def _regulated_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-compliance",
            "status": "approved",
            "domain": "healthcare",
            "category": "patient-automation",
        },
        "project": {
            "title": "Patient Intake Automation",
            "summary": "Automate patient intake review and nurse follow-up.",
            "target_users": "clinical operations teams",
            "specific_user": "intake nurse",
            "buyer": "clinic operations director",
            "workflow_context": "Patient form submission to nurse triage queue",
        },
        "problem": {
            "statement": "Teams copy patient emails and PII into spreadsheets without consent review.",
            "current_workaround": "Manual exports of patient account data and deletion requests.",
        },
        "solution": {
            "technical_approach": (
                "FastAPI service using OAuth, RBAC roles, audit logs, OpenAI summary prompts, "
                "Slack notifications, and Salesforce account updates."
            ),
            "suggested_stack": {
                "backend": "FastAPI",
                "database": "Postgres",
                "crm": "Salesforce",
                "messaging": "Slack",
                "ai": "OpenAI",
            },
        },
        "execution": {
            "mvp_scope": [
                "Patient intake queue",
                "Accessibility reviewed nurse dashboard",
                "Salesforce update",
            ],
            "validation_plan": "Run production-like audit log review and GDPR deletion fixture.",
            "risks": [
                "HIPAA policy and patient data retention may block launch.",
                "Slack integration could expose patient data.",
            ],
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
        },
    }


def test_generate_compliance_checklist_is_deterministic_and_complete() -> None:
    first = generate_compliance_checklist(_regulated_tact_spec())
    second = generate_compliance_checklist(_regulated_tact_spec())

    assert first == second
    assert first["schema_version"] == COMPLIANCE_CHECKLIST_SCHEMA_VERSION
    assert first["kind"] == "max.compliance_checklist"
    assert first["source"]["idea_id"] == "bu-compliance"
    assert first["summary"]["title"] == "Patient Intake Automation"
    assert first["summary"]["domain_risk_level"] == "high"
    assert first["summary"]["blocking_item_count"] >= 6
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "compliance_context",
        "sections",
        "checklist_items",
        "empty_state_guidance",
    }
    assert [section["id"] for section in first["sections"]] == [
        "privacy",
        "security",
        "data_governance",
        "regulatory",
        "accessibility",
        "ai_policy",
        "third_party",
        "launch_governance",
    ]
    assert [item["id"] for item in first["checklist_items"]] == [
        f"COMP{index}" for index in range(1, 9)
    ]
    assert all(item["owner"] for item in first["checklist_items"])
    assert all(item["evidence_needed"] for item in first["checklist_items"])
    assert all(item["remediation_guidance"] for item in first["checklist_items"])
    assert {"OpenAI", "Postgres", "Salesforce", "Slack"} <= set(
        first["compliance_context"]["detected_integrations"]
    )


def test_high_risk_domain_produces_blocking_remediation_items() -> None:
    checklist = generate_compliance_checklist(_regulated_tact_spec())

    regulatory = next(item for item in checklist["checklist_items"] if item["id"] == "COMP4")
    privacy = next(item for item in checklist["checklist_items"] if item["id"] == "COMP1")
    data = next(item for item in checklist["checklist_items"] if item["id"] == "COMP3")

    assert regulatory["blocking"] is True
    assert regulatory["owner"] == "compliance_owner"
    assert "legal, compliance, or policy owners" in regulatory["remediation_guidance"]
    assert "HIPAA" in regulatory["evidence_needed"]
    assert privacy["blocking"] is True
    assert "patient" in privacy["evidence_needed"]
    assert data["blocking"] is True
    assert "retention periods" in data["remediation_guidance"]


def test_render_compliance_checklist_json_round_trips() -> None:
    checklist = generate_compliance_checklist(_regulated_tact_spec())
    rendered = render_compliance_checklist_json(checklist)

    assert json.loads(rendered) == checklist
    assert rendered.endswith("\n")


def test_render_compliance_checklist_markdown_has_stable_sections_and_empty_guidance() -> None:
    checklist = generate_compliance_checklist(_regulated_tact_spec())

    first = render_compliance_checklist_markdown(checklist)
    second = render_compliance_checklist_markdown(checklist)

    assert first == second
    assert first.startswith("# Patient Intake Automation Compliance Checklist")
    assert f"- Schema version: {COMPLIANCE_CHECKLIST_SCHEMA_VERSION}" in first
    assert "## Compliance Context" in first
    assert "## Privacy and Personal Data" in first
    assert "## Security and Access Control" in first
    assert "## Data Governance" in first
    assert "## Regulatory Review" in first
    assert "## Accessibility" in first
    assert "## AI and Automation Policy" in first
    assert "## Third-Party Integrations" in first
    assert "## Launch Governance" in first
    assert "## Empty-State Guidance" in first
    assert "### COMP4: Obtain regulated-domain or policy owner review" in first
    assert "- Blocking: True" in first
    assert "Resolve blocking checklist items before implementation handoff" in first


def test_sparse_spec_keeps_empty_state_guidance_and_advisory_items() -> None:
    checklist = generate_compliance_checklist(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "evaluation": None,
        }
    )

    assert checklist["summary"]["title"] == "bu-sparse"
    assert checklist["summary"]["domain_risk_level"] == "standard"
    assert checklist["summary"]["blocking_item_count"] == 0
    assert checklist["empty_state_guidance"].startswith("No specialized compliance trigger")
    assert any(
        item["id"] == "COMP8" and not item["blocking"] for item in checklist["checklist_items"]
    )
    assert not any(item["id"] == "COMP4" and item["blocking"] for item in checklist["checklist_items"])
    markdown = render_compliance_checklist_markdown(checklist)
    assert "## Empty-State Guidance" in markdown
    assert "record product-owner signoff" in markdown


def test_compliance_checklist_is_importable_from_spec_package() -> None:
    checklist = exported_generate(_regulated_tact_spec())
    markdown = exported_render_markdown(checklist)
    rendered_json = exported_render_json(checklist)

    assert checklist["schema_version"] == COMPLIANCE_CHECKLIST_SCHEMA_VERSION
    assert markdown.startswith("# Patient Intake Automation Compliance Checklist")
    assert json.loads(rendered_json)["kind"] == "max.compliance_checklist"
