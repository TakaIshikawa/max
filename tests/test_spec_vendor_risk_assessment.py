from __future__ import annotations

import csv
from io import StringIO
import json

from max.spec import generate_vendor_risk_assessment as exported_generate
from max.spec import render_vendor_risk_assessment_csv as exported_render_csv
from max.spec import render_vendor_risk_assessment_markdown as exported_render
from max.spec.vendor_risk_assessment import (
    KIND,
    VENDOR_RISK_ASSESSMENT_CSV_COLUMNS,
    VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION,
    generate_vendor_risk_assessment,
    render_vendor_risk_assessment_csv,
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
    assert any(
        "privacy, security, and legal review" in item
        for item in by_name["Slack"]["review_requirements"]
    )

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
    assert "Complete vendor inventory" in {item["title"] for item in assessment["review_checklist"]}
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


def test_render_vendor_risk_assessment_csv_has_stable_headers_and_sections() -> None:
    assessment = generate_vendor_risk_assessment(_rich_spec())

    first = render_vendor_risk_assessment_csv(assessment)
    second = render_vendor_risk_assessment_csv(assessment)
    reader = csv.DictReader(StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(VENDOR_RISK_ASSESSMENT_CSV_COLUMNS)
    assert {row["section"] for row in rows} == {
        "vendors",
        "risks",
        "mitigations",
        "review_checklist",
        "gate_decision",
    }
    assert all(row["source_idea_id"] == "bu-vendor-risk" for row in rows)
    assert all(row["title"] == "Patient Follow-Up Automation" for row in rows)


def test_render_vendor_risk_assessment_csv_includes_representative_rows() -> None:
    assessment = generate_vendor_risk_assessment(_rich_spec())

    rows = list(csv.DictReader(StringIO(render_vendor_risk_assessment_csv(assessment))))

    vendor = next(
        row for row in rows if row["section"] == "vendors" and row["item_name"] == "OpenAI"
    )
    assert vendor["item_type"] == "vendor"
    assert vendor["category"] == "ai_provider"
    assert vendor["severity_or_status"] == "high"
    assert "patient data" in vendor["context"]
    assert "solution.suggested_stack.ai" in vendor["evidence"]
    assert "privacy, security, and legal review" in vendor["details"]

    risk = next(row for row in rows if row["item_id"] == "VRA-R01")
    assert risk["section"] == "risks"
    assert risk["item_name"] == "Sensitive data may be exchanged with vendors"
    assert risk["category"] == "sensitive_vendor_transfer"
    assert risk["severity_or_status"] == "high"
    assert "privacy_impact_assessment" in risk["evidence"]

    gate = next(row for row in rows if row["section"] == "gate_decision")
    assert gate["item_id"] == "gate_decision"
    assert gate["severity_or_status"] == "blocked"
    assert "privacy_owner" in gate["owner"]
    assert "Sensitive data may be exchanged with vendors" in gate["evidence"]
    assert "blocked when vendor inventory is missing" in gate["context"]


def test_render_vendor_risk_assessment_csv_flattens_optional_vendor_workflow_fields() -> None:
    assessment = {
        "schema_version": VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION,
        "kind": KIND,
        "source": {"idea_id": "bu-tabular-vra"},
        "summary": {"title": "Vendor CSV Console"},
        "vendors": [
            {
                "id": "VEND01",
                "name": "Acme AI",
                "category": "ai_provider",
                "risk_level": "high",
                "owner": "privacy_owner",
                "source_fields": ["solution.suggested_stack.ai"],
                "data_exposure": ["customer notes", "prompt metadata"],
                "mitigation": "Restrict prompts to approved fields.",
                "compliance_context": "DPA and SOC 2 required.",
                "renewal_date": "2026-11-15",
                "next_review_date": "2026-08-15",
                "fallback_strategy": "Route cases to manual review queue.",
            },
            {
                "id": "VEND02",
                "name": "LedgerCloud",
                "category": "payments",
                "risk_level": "medium",
                "business_owner": "finance_owner",
                "data_exchanged": ["invoice totals"],
                "review_date": "2026-07-01",
            },
        ],
        "external_services": [
            {
                "id": "SVC01",
                "name": "Webhook relay",
                "category": "integration",
                "owner": "engineering_owner",
                "data_exposure": "signed callbacks",
            }
        ],
        "risk_findings": [
            {
                "id": "FIND01",
                "title": "Prompt retention is unclear",
                "category": "data_retention",
                "severity": "high",
                "owner": "ai_owner",
                "description": "Provider terms must be confirmed.",
                "mitigation": "Attach retention evidence before launch.",
                "compliance_context": "GDPR processor review.",
            },
            {
                "id": "FIND02",
                "title": "Fallback ownership is split",
                "category": "operational_resilience",
                "severity": "medium",
                "owner": "operations_owner",
                "mitigations": ["Name an on-call owner.", "Document manual queue handoff."],
            },
        ],
        "review_owners": [{"owner": "legal_owner", "responsibility": "Approve DPA."}],
        "compliance_notes": [{"framework": "SOC 2", "note": "Map vendor report controls."}],
        "data_exposure": [{"data": "customer notes", "classification": "confidential"}],
        "fallback_strategies": ["Switch intake to spreadsheet export."],
    }

    rows = list(csv.DictReader(StringIO(render_vendor_risk_assessment_csv(assessment))))

    acme = next(row for row in rows if row["section"] == "vendors" and row["item_id"] == "VEND01")
    assert acme["owner"] == "privacy_owner"
    assert "Restrict prompts to approved fields." in acme["details"]
    assert "DPA and SOC 2 required." in acme["context"]
    assert "customer notes" in acme["context"]
    assert "renewal_date=2026-11-15" in acme["context"]
    assert "Route cases to manual review queue." in acme["context"]

    finding = next(row for row in rows if row["item_id"] == "FIND01")
    assert finding["section"] == "risks"
    assert finding["owner"] == "ai_owner"
    assert finding["details"] == "Attach retention evidence before launch."
    assert "GDPR processor review." in finding["context"]

    sections = {row["section"] for row in rows}
    assert "external_services" in sections
    assert "review_owners" in sections
    assert "compliance_notes" in sections
    assert "data_exposure" in sections
    assert "renewal_review_dates" in sections
    assert "fallback_strategies" in sections


def test_render_vendor_risk_assessment_csv_quotes_special_characters() -> None:
    assessment = {
        "schema_version": VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION,
        "kind": KIND,
        "source": {"idea_id": "bu-quoted"},
        "summary": {"title": 'Quoted, "Risk" Export'},
        "vendors": [
            {
                "id": "VEND01",
                "name": 'ACME, "AI"',
                "category": "ai_provider",
                "risk_level": "high",
                "owner": "legal_owner",
                "data_exposure": ["line one\nline two", "customer, invoice"],
                "mitigation": 'Require "no training" terms, DPA, and audit rights.',
            }
        ],
    }

    csv_text = render_vendor_risk_assessment_csv(assessment)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Quoted, ""Risk"" Export"' in csv_text
    assert '"ACME, ""AI"""' in csv_text
    assert rows[0]["title"] == 'Quoted, "Risk" Export'
    assert rows[0]["item_name"] == 'ACME, "AI"'
    assert "line one line two" in rows[0]["context"]
    assert 'Require "no training" terms, DPA, and audit rights.' in rows[0]["details"]


def test_render_vendor_risk_assessment_csv_handles_minimal_assessment_dicts() -> None:
    csv_text = render_vendor_risk_assessment_csv({})
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert rows == []
    assert csv_text == ",".join(VENDOR_RISK_ASSESSMENT_CSV_COLUMNS) + "\n"


def test_vendor_risk_assessment_is_json_stable() -> None:
    first = generate_vendor_risk_assessment(_rich_spec())
    second = generate_vendor_risk_assessment(_rich_spec())

    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_vendor_risk_assessment_is_importable_from_spec_package() -> None:
    assessment = exported_generate(_rich_spec())
    markdown = exported_render(assessment)
    csv_text = exported_render_csv(assessment)

    assert assessment["schema_version"] == VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION
    assert markdown.startswith("# Patient Follow-Up Automation Vendor Risk Assessment")
    assert csv_text.startswith(",".join(VENDOR_RISK_ASSESSMENT_CSV_COLUMNS))
