"""Tests for design brief partner integration checklist generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_partner_integration_checklist import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_partner_integration_checklist,
    partner_integration_checklist_filename,
    render_design_brief_partner_integration_checklist,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_partner_integration_checklist_complete_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_partner_integration_checklist(store, brief_id)
        repeated = build_design_brief_partner_integration_checklist(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["target_user"] == "customer success operator"
    assert report["summary"]["buyer"] == "customer success director"
    assert report["summary"]["workflow_context"] == "CRM-to-Slack launch handoff"
    assert report["summary"]["fallbacks_used"] == []
    assert [target["id"] for target in report["integration_targets"]] == [
        "core_product",
        "salesforce_crm",
        "slack",
        "postgres",
        "oauth_sso",
        "webhook_api",
    ]
    assert report["integration_targets"][1]["owner"] == "CRM partner"
    assert report["integration_targets"][1]["priority"] == "high"
    assert report["integration_targets"][1]["validation_action"]
    assert "sig-partner" in report["integration_targets"][1]["source_reference_ids"]
    assert [contract["id"] for contract in report["data_contracts"]] == ["DC1", "DC2"]
    assert all(
        {"owner", "priority", "validation_action", "source_reference_ids"} <= set(item)
        for item in [
            *report["data_contracts"],
            *report["auth_and_security_checks"],
            *report["operational_readiness"],
        ]
    )
    assert report["data_contracts"][0]["consumer"] == "Salesforce CRM"
    assert report["auth_and_security_checks"][0]["owner"] == "Security owner"
    assert report["operational_readiness"][0]["check"] == "Sandbox and fixture readiness"
    assert report["partner_owner_matrix"][1]["partner"] == "Salesforce CRM"
    assert [item["id"] for item in report["sequencing"]] == ["SEQ1", "SEQ2", "SEQ3", "SEQ4"]
    assert report["open_questions"][0]["owner"] == "CRM partner"
    assert {reference["id"] for reference in report["evidence_references"]} >= {
        "design_brief.why_this_now",
        "design_brief.synthesis_rationale",
        "design_brief.validation_plan",
        "sig-partner",
        "ins-partner",
    }
    assert report["readiness_warnings"] == []
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_build_design_brief_partner_integration_checklist_sparse_brief(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "sparse_partner_integration.db"), wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-partner-sparse",
            title="Sparse Partner Source",
            one_liner="Sparse source for partner integration fallbacks.",
            category="application",
            problem="",
            solution="",
            value_proposition="",
            specific_user="",
            buyer="",
            workflow_context="",
            current_workaround="",
            why_now="",
            validation_plan="",
            first_10_customers="",
            domain_risks=[],
            evidence_signals=[],
            inspiring_insights=[],
            tech_approach="",
            suggested_stack={},
            domain="",
            status="draft",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Sparse Partner Brief",
                domain="",
                theme="",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=39.0,
                why_this_now="",
                merged_product_concept="",
                synthesis_rationale="",
                mvp_scope=[],
                first_milestones=[],
                validation_plan="",
                risks=[],
                source_idea_ids=[lead.id],
                design_status="draft",
            )
        )
        report = build_design_brief_partner_integration_checklist(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["target_user"] == "Sparse Partner Brief user"
    assert report["summary"]["buyer"] == "integration sponsor"
    assert report["summary"]["workflow_context"] == "Sparse Partner Brief workflow"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "merged_product_concept",
    ]
    assert [target["id"] for target in report["integration_targets"]] == [
        "core_product",
        "customer_workflow_system",
    ]
    assert report["data_contracts"][0]["required_fields"]
    assert report["auth_and_security_checks"]
    assert report["operational_readiness"]
    assert report["open_questions"][-1]["id"] == "OQ3"
    assert report["evidence_references"] == []
    assert [warning["severity"] for warning in report["readiness_warnings"]] == [
        "high",
        "high",
        "medium",
        "medium",
        "medium",
        "medium",
        "medium",
        "medium",
    ]


def test_render_design_brief_partner_integration_checklist_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_partner_integration_checklist(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_partner_integration_checklist(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_partner_integration_checklist(report, fmt="markdown")
    default_markdown = render_design_brief_partner_integration_checklist(report)
    assert markdown == default_markdown
    assert markdown == render_design_brief_partner_integration_checklist(report, fmt="markdown")
    assert markdown.startswith("# Partner Integration Checklist: Partner Integration Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Integration Targets" in markdown
    assert "### Salesforce CRM" in markdown
    assert "## Data Contracts" in markdown
    assert "## Auth and Security Checks" in markdown
    assert "## Operational Readiness" in markdown
    assert "## Partner Owner Matrix" in markdown
    assert "## Sequencing" in markdown
    assert "## Open Questions" in markdown
    assert "## Evidence References" in markdown
    assert "## Readiness Warnings" in markdown
    assert "### Salesforce CRM" in markdown
    assert markdown.index("### Salesforce CRM") < markdown.index("### Slack")
    assert "- Required fields: record_id; user_id; workflow_state; owner; timestamp" in markdown
    assert "- **sig-partner** (evidence_signal): Evidence signal linked to source idea bu-partner-lead." in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    with pytest.raises(ValueError, match="Unsupported partner integration checklist format: yaml"):
        render_design_brief_partner_integration_checklist(report, fmt="yaml")


def test_render_design_brief_partner_integration_checklist_csv_populated_output(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_partner_integration_checklist(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered = render_design_brief_partner_integration_checklist(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(rendered)))

    assert rendered.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows
    assert set(rows[0]) == set(CSV_COLUMNS)
    assert {row["design_brief_id"] for row in rows} == {brief_id}
    assert {row["design_brief_title"] for row in rows} == {"Partner Integration Brief"}
    assert {row["section"] for row in rows} == {
        "integration_targets",
        "data_contracts",
        "auth_and_security_checks",
        "operational_readiness",
        "partner_owner_matrix",
        "sequencing",
        "open_questions",
    }

    salesforce = next(
        row
        for row in rows
        if row["section"] == "integration_targets" and row["target_id"] == "salesforce_crm"
    )
    assert salesforce["row_type"] == "target"
    assert salesforce["target_name"] == "Salesforce CRM"
    assert salesforce["target_type"] == "crm"
    assert salesforce["owner"] == "CRM partner"
    assert json.loads(salesforce["source_reference_ids"]) == [
        "design_brief.synthesis_rationale",
        "design_brief.validation_plan",
        "design_brief.why_this_now",
        "ins-partner",
        "sig-partner",
        "sig-support",
    ]

    contract = next(
        row
        for row in rows
        if row["section"] == "data_contracts" and row["item_id"] == "DC1"
    )
    assert contract["row_type"] == "data_contract"
    assert contract["producer"] == "Partner Integration Brief"
    assert contract["consumer"] == "Salesforce CRM"
    assert json.loads(contract["required_fields"]) == [
        "owner",
        "record_id",
        "timestamp",
        "user_id",
        "workflow_state",
    ]

    sequence = next(
        row
        for row in rows
        if row["section"] == "sequencing" and row["item_id"] == "SEQ2"
    )
    assert sequence["row_type"] == "sequence_item"
    assert sequence["sequence"] == "2"
    assert sequence["target_id"] == "salesforce_crm"


def test_render_design_brief_partner_integration_checklist_csv_is_deterministic_and_escapes(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_partner_integration_checklist(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["design_brief"]["title"] = 'Partner, "Integration"\nBrief'
    report["integration_targets"][0]["name"] = 'Core, "Product"\nApp'
    report["integration_targets"][0]["reason"] = 'Line one, "quoted"\nline two'
    report["integration_targets"][0]["source_reference_ids"] = ["z-ref", "a-ref"]

    first = render_design_brief_partner_integration_checklist(report, fmt="csv")
    second = render_design_brief_partner_integration_checklist(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(first)))

    assert first == second
    assert '"Partner, ""Integration""\nBrief"' in first
    assert '"Core, ""Product""\nApp"' in first
    target = next(
        row
        for row in rows
        if row["section"] == "integration_targets" and row["item_id"] == "core_product"
    )
    assert target["design_brief_title"] == 'Partner, "Integration"\nBrief'
    assert target["target_name"] == 'Core, "Product"\nApp'
    assert json.loads(target["source_reference_ids"]) == ["a-ref", "z-ref"]
    assert json.loads(target["details"]) == {"reason": 'Line one, "quoted"\nline two'}


def test_partner_integration_checklist_csv_header_only_for_empty_sections() -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "design_brief": {"id": "dbf-empty", "title": "Empty Partner Brief"},
        "integration_targets": [],
        "data_contracts": [],
        "auth_and_security_checks": [],
        "operational_readiness": [],
        "partner_owner_matrix": [],
        "sequencing": [],
        "open_questions": [],
        "readiness_warnings": [],
    }

    rendered = render_design_brief_partner_integration_checklist(report, fmt="csv")
    reader = csv.DictReader(io.StringIO(rendered))

    assert rendered == ",".join(CSV_COLUMNS) + "\n"
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert list(reader) == []


def test_render_design_brief_partner_integration_checklist_minimal_report() -> None:
    markdown = render_design_brief_partner_integration_checklist(
        {
            "design_brief": {
                "id": "dbf-minimal",
                "title": "Minimal Partner Brief",
            },
            "summary": {},
        }
    )

    assert markdown.startswith("# Partner Integration Checklist: Minimal Partner Brief")
    assert "Design brief: `dbf-minimal`" in markdown
    assert "- Goal: Confirm partner and system readiness for Minimal Partner Brief." in markdown
    assert "- Target user: TBD target user" in markdown
    assert "- Buyer: TBD buyer owner" in markdown
    assert "## Integration Targets" in markdown
    assert "No partner systems identified yet" in markdown
    assert "## Data Contracts" in markdown
    assert "Capture producer, consumer, payload, required fields" in markdown
    assert "## Auth and Security Checks" in markdown
    assert "credential ownership" in markdown
    assert "## Operational Readiness" in markdown
    assert "Prepare sandbox access" in markdown
    assert "| TBD partner system | TBD owner | medium | Assign owner and confirm handoff criteria. |" in markdown
    assert "### 1. Confirm partner scope and owner" in markdown
    assert "## Open Questions" in markdown
    assert "## Evidence References" in markdown
    assert "## Readiness Warnings" in markdown


def test_partner_integration_checklist_filename_uses_brief_id_and_title() -> None:
    assert (
        partner_integration_checklist_filename(
            {"id": "dbf-123", "title": "Partner Systems: Alpha / Beta"}
        )
        == "dbf-123-Partner-Systems-Alpha-Beta-partner-integration-checklist.md"
    )
    assert (
        partner_integration_checklist_filename(
            {"id": "dbf-123", "title": "Partner Systems: Alpha / Beta"}, fmt="json"
        )
        == "dbf-123-Partner-Systems-Alpha-Beta-partner-integration-checklist.json"
    )
    assert (
        partner_integration_checklist_filename(
            {"id": "dbf-123", "title": "Partner Systems: Alpha / Beta"}, fmt="csv"
        )
        == "dbf-123-Partner-Systems-Alpha-Beta-partner-integration-checklist.csv"
    )


def test_build_design_brief_partner_integration_checklist_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_partner_integration.db"), wal_mode=True)
    try:
        report = build_design_brief_partner_integration_checklist(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "partner_integration.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-partner-lead",
        title="Partner Integration Lead",
        one_liner="Coordinate CRM and collaboration integration readiness.",
        category="application",
        problem="Launch handoffs span Salesforce, Slack, and internal APIs without readiness checks.",
        solution="Generate integration targets, data contracts, and security checks from design briefs.",
        value_proposition="Make partner readiness explicit before implementation handoff.",
        specific_user="customer success operator",
        buyer="customer success director",
        workflow_context="CRM-to-Slack launch handoff",
        current_workaround="manual Salesforce updates and Slack pings",
        why_now="External partner dependencies are appearing in generated specs.",
        validation_plan="Run a Salesforce sandbox sync and Slack notification dry run.",
        first_10_customers="customer success teams managing launch handoffs",
        domain_risks=["OAuth token scope may be too broad for customer data."],
        evidence_signals=["sig-partner"],
        inspiring_insights=["ins-partner"],
        tech_approach="FastAPI webhook API with Salesforce CRM sync, Slack notifications, OAuth, and Postgres.",
        suggested_stack={
            "backend": "FastAPI",
            "crm": "Salesforce",
            "messaging": "Slack",
            "auth": "OAuth",
            "database": "Postgres",
        },
        domain="customer-success",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-partner-support",
        title="Partner Integration Support",
        one_liner="Add partner rollback and monitoring checks.",
        category="application",
        problem="Partner failures lack explicit support ownership.",
        solution="Add operational readiness checks for integration launches.",
        value_proposition="Reduce launch risk for partner-backed workflows.",
        specific_user="support lead",
        buyer="operations director",
        workflow_context="partner support escalation",
        domain_risks=["Partner downtime may block pilot completion."],
        evidence_signals=["sig-support"],
        tech_approach="Webhook retries and support monitoring for API integrations.",
        suggested_stack={"api": "webhook"},
        domain="customer-success",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Partner Integration Brief",
            domain="customer-success",
            theme="partner-readiness",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=86.0,
            why_this_now="Generated specs imply Salesforce, Slack, OAuth, and API partner dependencies.",
            merged_product_concept="A deterministic partner integration checklist for design brief handoff.",
            synthesis_rationale="Makes system owners, data contracts, and security readiness explicit.",
            mvp_scope=["Salesforce status sync", "Slack launch notification"],
            first_milestones=["Complete Salesforce sandbox sync"],
            validation_plan="Run a Salesforce sandbox sync and Slack notification dry run.",
            risks=["OAuth token scope may be too broad for customer data."],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )
    return store, brief_id
