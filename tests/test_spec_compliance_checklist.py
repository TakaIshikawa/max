from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec import generate_compliance_checklist as exported_generate
from max.spec import render_compliance_checklist_csv as exported_render_csv
from max.spec import render_compliance_checklist_json as exported_render_json
from max.spec import render_compliance_checklist_markdown as exported_render_markdown
from max.spec.compliance_checklist import (
    COMPLIANCE_CHECKLIST_CSV_COLUMNS,
    COMPLIANCE_CHECKLIST_SCHEMA_VERSION,
    generate_compliance_checklist,
    render_compliance_checklist_csv,
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


def test_render_compliance_checklist_csv_flattens_high_risk_rows_and_context() -> None:
    checklist = generate_compliance_checklist(_regulated_tact_spec())

    csv_output = render_compliance_checklist_csv(checklist)
    rows = list(csv.DictReader(StringIO(csv_output)))

    assert csv.DictReader(StringIO(csv_output)).fieldnames == COMPLIANCE_CHECKLIST_CSV_COLUMNS
    assert [row["item_id"] for row in rows] == [f"COMP{index}" for index in range(1, 9)]
    assert all(row["schema_version"] == COMPLIANCE_CHECKLIST_SCHEMA_VERSION for row in rows)
    assert all(row["source_idea_id"] == "bu-compliance" for row in rows)
    assert all(row["title"] == "Patient Intake Automation" for row in rows)
    assert all(row["domain"] == "healthcare" for row in rows)
    assert all(row["domain_risk_level"] == "high" for row in rows)

    privacy = rows[0]
    assert privacy["section_id"] == "privacy"
    assert privacy["section_title"] == "Privacy and Personal Data"
    assert privacy["category"] == "privacy"
    assert privacy["blocking"] == "true"
    assert privacy["owner"] == "privacy_owner"
    assert privacy["status"] == "open"
    assert privacy["requirement"] == "Confirm personal data classification and user notice"
    assert "patient" in privacy["evidence_needed"]
    assert "patient" in privacy["source_fields"]

    regulatory = next(row for row in rows if row["item_id"] == "COMP4")
    assert regulatory["blocking"] == "true"
    assert regulatory["section_title"] == "Regulatory Review"
    assert "HIPAA" in regulatory["evidence_needed"]

    launch = next(row for row in rows if row["item_id"] == "COMP8")
    assert launch["blocking"] == "true"
    assert launch["empty_state_guidance"].startswith("Resolve blocking checklist items")

    assert privacy["detected_data_terms"] == (
        "account; consent; email; export; patient; PII; retention"
    )
    assert privacy["detected_integrations"] == "OAuth; OpenAI; Postgres; Salesforce; Slack; Teams"


def test_render_compliance_checklist_csv_empty_state_when_no_items_exist() -> None:
    checklist = {
        "schema_version": COMPLIANCE_CHECKLIST_SCHEMA_VERSION,
        "kind": "max.compliance_checklist",
        "source": {"idea_id": "bu-empty", "status": "draft", "type": "idea"},
        "summary": {
            "title": "Empty Checklist",
            "domain_risk_level": "standard",
        },
        "compliance_context": {
            "domain": "internal-tools",
            "detected_data_terms": [],
            "detected_integrations": [],
        },
        "sections": [],
        "checklist_items": [],
        "empty_state_guidance": "No compliance items were generated.",
    }

    csv_output = render_compliance_checklist_csv(checklist)
    rows = list(csv.DictReader(StringIO(csv_output)))

    assert len(rows) == 1
    assert rows[0]["source_idea_id"] == "bu-empty"
    assert rows[0]["title"] == "Empty Checklist"
    assert rows[0]["domain"] == "internal-tools"
    assert rows[0]["item_id"] == ""
    assert rows[0]["blocking"] == ""
    assert rows[0]["empty_state_guidance"] == "No compliance items were generated."


def test_render_compliance_checklist_csv_is_deterministic_for_missing_optional_fields() -> None:
    checklist = {
        "schema_version": COMPLIANCE_CHECKLIST_SCHEMA_VERSION,
        "kind": "max.compliance_checklist",
        "source": {"idea_id": "bu-minimal"},
        "summary": {"title": "Minimal"},
        "sections": [
            {
                "id": "third_party",
                "title": "Third-Party Integrations",
                "items": [
                    {
                        "id": "COMP7",
                        "category": "third_party",
                        "title": "Validate integrations",
                        "blocking": False,
                    }
                ],
            }
        ],
        "empty_state_guidance": None,
        "unsupported": {"ignored": True},
    }

    first = render_compliance_checklist_csv(checklist)
    second = render_compliance_checklist_csv(checklist | {"another_unsupported": ["ignored"]})
    rows = list(csv.DictReader(StringIO(first)))

    assert first == second
    assert rows[0]["owner"] == ""
    assert rows[0]["status"] == ""
    assert rows[0]["blocking"] == "false"
    assert rows[0]["evidence_needed"] == ""
    assert rows[0]["source_fields"] == ""


def test_render_compliance_checklist_csv_orders_scrambled_sections_and_items() -> None:
    checklist = generate_compliance_checklist(_regulated_tact_spec())
    checklist["sections"] = [
        checklist["sections"][2],
        checklist["sections"][0],
        {
            **checklist["sections"][1],
            "items": [
                {**checklist["sections"][1]["items"][0], "id": "COMP2B"},
                checklist["sections"][1]["items"][0],
            ],
        },
    ]
    checklist["checklist_items"] = []

    rows = list(csv.DictReader(StringIO(render_compliance_checklist_csv(checklist))))

    assert [(row["section_id"], row["item_id"]) for row in rows] == [
        ("privacy", "COMP1"),
        ("security", "COMP2"),
        ("security", "COMP2B"),
        ("data_governance", "COMP3"),
    ]


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
    csv_output = exported_render_csv(checklist)
    rendered_json = exported_render_json(checklist)

    assert checklist["schema_version"] == COMPLIANCE_CHECKLIST_SCHEMA_VERSION
    assert markdown.startswith("# Patient Intake Automation Compliance Checklist")
    assert csv_output.startswith("schema_version,kind,source_idea_id")
    assert json.loads(rendered_json)["kind"] == "max.compliance_checklist"
