from __future__ import annotations

import json

from max.spec import generate_vendor_risk_assessment as exported_generate
from max.spec import render_vendor_risk_assessment_markdown as exported_render
from max.spec.vendor_risk_assessment import (
    KIND,
    VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION,
    generate_vendor_risk_assessment,
    render_vendor_risk_assessment_markdown,
)


def _rich_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-vendor-risk",
            "status": "approved",
            "domain": "healthcare",
            "category": "automation",
        },
        "project": {
            "title": "Patient Follow-Up Automation",
            "workflow_context": "patient intake to follow-up queue",
            "specific_user": "clinic coordinator",
            "buyer": "clinic operations director",
        },
        "problem": {
            "statement": "Teams copy patient emails and appointment notes into spreadsheets.",
            "current_workaround": "Manual HIPAA-sensitive review.",
        },
        "solution": {
            "technical_approach": "FastAPI service with OpenAI summaries, Salesforce sync, Slack alerts, OAuth, and Datadog logs.",
            "suggested_stack": {
                "ai": "OpenAI",
                "crm": "Salesforce",
                "messaging": "Slack",
                "observability": "Datadog",
                "database": "Supabase",
            },
        },
        "integrations": {"payments": "Stripe", "source_control": "GitHub"},
        "execution": {
            "risks": [
                "Patient PII must not leak to Slack or AI prompts.",
                "Vendor outage requires a queue retry and manual fallback path.",
            ],
        },
        "artifacts": {
            "privacy_impact_assessment": {
                "personal_data": [
                    {"id": "patient_data", "label": "patient data"},
                    {"id": "email", "label": "email addresses"},
                ]
            },
            "data_classification": {
                "categories": [
                    {"id": "regulated", "label": "regulated health data"},
                ]
            },
            "deployment_topology": {
                "nodes": [
                    {"name": "managed Supabase database", "provider": "Supabase"},
                    {"name": "Datadog log drain", "provider": "Datadog"},
                ],
                "notes": "Queue retry, fallback workflow, US region, DPA, BAA, SLA, and SOC 2 evidence required.",
            },
            "dependency_inventory": {
                "dependencies": [
                    {"name": "OpenAI", "type": "external_service", "risk_level": "high"},
                    {"name": "Slack", "type": "integration", "risk_level": "high"},
                ],
            },
            "security_review": {
                "controls": ["OAuth scopes, secrets handling, audit logging, and vendor review."],
            },
        },
    }


def test_generate_vendor_risk_assessment_extracts_vendors_and_review_requirements() -> None:
    assessment = generate_vendor_risk_assessment(_rich_spec())

    assert assessment["schema_version"] == VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION
    assert assessment["kind"] == KIND
    assert assessment["source"]["idea_id"] == "bu-vendor-risk"
    assert assessment["summary"]["vendor_count"] >= 6
    assert assessment["summary"]["high_risk_vendor_count"] >= 3
    assert assessment["gate_decision"]["status"] == "blocked"
    assert set(assessment) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "vendors",
        "risks",
        "mitigations",
        "review_checklist",
        "gate_decision",
    }

    by_name = {vendor["name"]: vendor for vendor in assessment["vendors"]}
    assert by_name["OpenAI"]["category"] == "ai_provider"
    assert by_name["OpenAI"]["risk_level"] == "high"
    assert "patient data" in by_name["OpenAI"]["data_exchanged"]
    assert "regulated health data" in by_name["OpenAI"]["data_exchanged"]
    assert "prompts, derived outputs, logs, or telemetry" in by_name["OpenAI"]["data_exchanged"]
    assert "Salesforce" in by_name
    assert "Slack" in by_name
    assert "Datadog" in by_name
    assert any("privacy, security, and legal review" in item for item in by_name["Slack"]["review_requirements"])

    categories = {risk["category"] for risk in assessment["risks"]}
    assert "sensitive_vendor_transfer" in categories
    assert "critical_vendor_dependency" in categories
    assert "contract_evidence_gap" not in categories
    assert "vendor_outage_gap" not in categories
    assert "privacy_owner" in assessment["gate_decision"]["required_reviews"]


def test_sparse_specs_emit_actionable_missing_input_risks() -> None:
    assessment = generate_vendor_risk_assessment({"schema_version": "tact-spec-preview/v1"})

    assert assessment["kind"] == KIND
    assert assessment["summary"]["vendor_count"] == 1
    assert assessment["summary"]["gate_status"] == "blocked"
    assert assessment["vendors"][0]["name"] == "Unspecified external vendor"
    assert assessment["vendors"][0]["risk_level"] == "high"
    assert "missing_vendor_inventory" in {risk["category"] for risk in assessment["risks"]}
    assert "Complete vendor inventory" in {
        item["title"] for item in assessment["review_checklist"]
    }
    assert assessment["gate_decision"]["blocking_reasons"]


def test_render_vendor_risk_assessment_markdown_is_stable_and_traceable() -> None:
    assessment = generate_vendor_risk_assessment(_rich_spec())

    first = render_vendor_risk_assessment_markdown(assessment)
    second = render_vendor_risk_assessment_markdown(assessment)

    assert first == second
    assert first.startswith("# Patient Follow-Up Automation Vendor Risk Assessment")
    assert f"- Schema version: {VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION}" in first
    for heading in [
        "## Vendors",
        "## Vendor Risks",
        "## Mitigations",
        "## Review Checklist",
        "## Gate Decision",
    ]:
        assert heading in first
    assert "OpenAI" in first
    assert "Sensitive data may be exchanged with vendors" in first
    assert "Gate decision: blocked" in first
    assert "Status: blocked" in first


def test_vendor_risk_assessment_is_json_stable() -> None:
    first = generate_vendor_risk_assessment(_rich_spec())
    second = generate_vendor_risk_assessment(_rich_spec())

    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_vendor_risk_assessment_is_importable_from_spec_package() -> None:
    assessment = exported_generate(_rich_spec())
    markdown = exported_render(assessment)

    assert assessment["schema_version"] == VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION
    assert markdown.startswith("# Patient Follow-Up Automation Vendor Risk Assessment")
