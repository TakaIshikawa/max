"""Tests for design brief integration contract generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis import build_design_brief_integration_contract as exported_build
from max.analysis import render_design_brief_integration_contract as exported_render
from max.analysis import render_integration_contract_csv as exported_render_csv
from max.analysis.design_brief_integration_contract import (
    CONTRACT_SECTION_IDS,
    INTEGRATION_CONTRACT_CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_integration_contract,
    render_design_brief_integration_contract,
    render_integration_contract_csv,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_integration_contract_representative_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_integration_contract(store, brief_id)
        repeated = build_design_brief_integration_contract(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert [section["id"] for section in report["contract_sections"]] == list(CONTRACT_SECTION_IDS)
    assert report["summary"]["section_count"] == len(CONTRACT_SECTION_IDS)
    assert [system["system"] for system in report["external_systems"]] == [
        "Salesforce",
        "Slack",
    ]
    assert report["external_systems"][0]["id"] == "ES1"
    assert report["external_systems"][0]["evidence_reference_id"] == "design_brief.merged_product_concept"
    assert report["data_contracts"][0]["id"] == "DC1"
    assert report["data_contracts"][0]["data_object"] == "Customer or account record"
    assert report["auth_assumptions"][0]["id"] == "AA1"
    assert report["auth_assumptions"][0]["assumption"] == "OAuth or SSO delegated access"
    assert report["api_webhook_contracts"][0]["id"] == "AWC1"
    assert report["failure_handling"][0]["id"] == "FH1"
    assert report["observability_hooks"][0]["id"] == "OH1"
    assert [question["id"] for question in report["open_questions"]] == ["OQ1", "OQ2", "OQ3"]
    assert {reference["id"] for reference in report["evidence_references"]} >= {
        "design_brief.merged_product_concept",
        "design_brief.validation_plan",
        "sig-integration-contract",
        "ins-integration-contract",
    }
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_build_design_brief_integration_contract_sparse_inputs_remain_actionable(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_integration_contract(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert [section["id"] for section in report["contract_sections"]] == list(CONTRACT_SECTION_IDS)
    assert report["external_systems"][0]["system"] == "External API or workflow tool"
    assert report["data_contracts"]
    assert report["auth_assumptions"]
    assert report["api_webhook_contracts"]
    assert report["failure_handling"]
    assert report["observability_hooks"]
    assert [question["id"] for question in report["open_questions"]] == ["OQ1", "OQ2", "OQ3", "OQ4"]
    assert "merged_product_concept" in report["summary"]["fallbacks_used"]
    assert "mvp_scope" in report["summary"]["fallbacks_used"]
    assert "risks" in report["summary"]["fallbacks_used"]
    assert all(item["evidence_reference_id"] for section in report["contract_sections"] for item in section["items"])


def test_render_design_brief_integration_contract_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_integration_contract(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_integration_contract(report, fmt="json")
    assert json.loads(rendered_json) == report
    assert render_design_brief_integration_contract(report, fmt="csv") == render_integration_contract_csv(report)

    markdown = render_design_brief_integration_contract(report, fmt="markdown")
    assert markdown.startswith("# Integration Contract: Integration Contract Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## External Systems" in markdown
    assert "## Data Contracts" in markdown
    assert "## Authentication and Authorization" in markdown
    assert "## API or Webhook Contracts" in markdown
    assert "## Failure Handling" in markdown
    assert "## Observability Hooks" in markdown
    assert "## Open Contract Questions" in markdown
    assert "### ES1: Salesforce" in markdown
    assert "### DC1: Customer or account record" in markdown
    assert "### AA1: OAuth or SSO delegated access" in markdown
    assert "Evidence reference id: design_brief.merged_product_concept" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    with pytest.raises(ValueError, match="Unsupported integration contract format: yaml"):
        render_design_brief_integration_contract(report, fmt="yaml")


def test_render_integration_contract_csv_headers_rows_and_multi_integration_order(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_integration_contract(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_output = render_integration_contract_csv(report)
    reader = csv.DictReader(io.StringIO(csv_output))
    rows = list(reader)

    assert reader.fieldnames == list(INTEGRATION_CONTRACT_CSV_COLUMNS)
    assert csv_output.splitlines()[0] == ",".join(INTEGRATION_CONTRACT_CSV_COLUMNS)
    assert [row["integration_name"] for row in rows] == ["Salesforce", "Slack"]
    assert [row["provider"] for row in rows] == ["Salesforce", "Slack"]
    assert rows[0]["owner"] == "Engineering owner"
    assert "Customer or account record" in rows[0]["data_exchanged"]
    assert "external_id; status; updated_at; owner_or_actor; source_system" in rows[0]["data_exchanged"]
    assert "OAuth or SSO delegated access" in rows[0]["auth_assumptions"]
    assert "External system unavailable or rate limited" in rows[0]["failure_modes"]
    assert "Integration health and latency" in rows[0]["sla_expectations"]
    assert "design_brief.merged_product_concept" in rows[0]["evidence"]
    assert "[" not in rows[0]["data_exchanged"]
    assert "{'" not in rows[0]["data_exchanged"]


def test_render_integration_contract_csv_escapes_and_blanks_optional_fields() -> None:
    report = {
        "external_systems": [
            {
                "system": 'Salesforce, "Enterprise"',
                "owner": "",
                "evidence_reference_id": "brief,1",
            },
            {"system": "Slack\nConnect"},
        ],
        "data_contracts": [
            {
                "data_object": 'Account, "renewal"',
                "required_fields": ["external_id", "status\nreason"],
                "validation_rules": [],
            }
        ],
        "auth_assumptions": [
            {
                "assumption": "",
                "scope_requirement": 'Use "least privilege", rotate monthly.',
                "authorization_check": None,
            }
        ],
        "failure_handling": [
            {
                "failure_mode": "Rate limit",
                "handling_requirement": "Retry,\nthen queue.",
                "user_impact": "",
            }
        ],
        "observability_hooks": [],
    }

    csv_output = render_integration_contract_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_output)))

    assert rows[0]["integration_name"] == 'Salesforce, "Enterprise"'
    assert rows[0]["owner"] == ""
    assert rows[0]["data_exchanged"] == (
        'Account, "renewal"; required_fields: external_id; status\nreason'
    )
    assert rows[0]["auth_assumptions"] == 'Use "least privilege", rotate monthly.'
    assert rows[0]["failure_modes"] == "Rate limit; Retry,\nthen queue."
    assert rows[0]["sla_expectations"] == ""
    assert rows[0]["evidence"] == "brief,1"
    assert rows[1]["integration_name"] == "Slack\nConnect"
    assert rows[1]["owner"] == ""
    assert rows[1]["evidence"] == ""
    assert '"Salesforce, ""Enterprise"""' in csv_output
    assert '"Slack\nConnect"' in csv_output
    assert '"Rate limit; Retry,\nthen queue."' in csv_output


def test_design_brief_integration_contract_empty_store_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_integration_contract.db"), wal_mode=True)
    try:
        report = build_design_brief_integration_contract(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def test_design_brief_integration_contract_is_importable_from_analysis_package(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = exported_build(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert exported_render(report).startswith("# Integration Contract: Integration Contract Brief")
    assert exported_render_csv(report).startswith(",".join(INTEGRATION_CONTRACT_CSV_COLUMNS))


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_integration_contract_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-integration-contract-sparse",
            title="Sparse Integration Contract Lead",
            one_liner="Create integration defaults when brief evidence is thin.",
            category="application",
            problem="",
            solution="",
            value_proposition="",
            specific_user="",
            buyer="",
            workflow_context="",
            current_workaround="",
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
        brief_kwargs = {
            "readiness_score": 35.0,
            "why_this_now": "",
            "merged_product_concept": "",
            "synthesis_rationale": "",
            "mvp_scope": [],
            "first_milestones": [],
            "validation_plan": "",
            "risks": [],
            "design_status": "draft",
        }
    else:
        lead = BuildableUnit(
            id="bu-integration-contract-lead",
            title="Integration Contract Lead",
            one_liner="Clarify external API boundaries before implementation handoff.",
            category="application",
            problem="Customer success teams need Salesforce data and Slack notifications without hidden contract gaps.",
            solution="Generate an integration contract for Salesforce sync, Slack webhooks, OAuth scopes, and observability.",
            value_proposition="Make third-party API boundaries explicit before build starts.",
            specific_user="customer success operator",
            buyer="customer success director",
            workflow_context="Salesforce to Slack renewal workflow",
            current_workaround="Manual Salesforce exports and Slack pings",
            why_now="Generated specs increasingly depend on external APIs and workflow tools.",
            validation_plan="Run Salesforce sandbox sync and Slack webhook dry run with OAuth scoped tokens.",
            first_10_customers="customer success teams using Salesforce and Slack",
            domain_risks=[
                "OAuth scopes and customer data retention need security and privacy review.",
            ],
            evidence_signals=["sig-integration-contract"],
            inspiring_insights=["ins-integration-contract"],
            tech_approach="FastAPI webhook endpoint with Salesforce, Slack, OAuth, and Postgres.",
            suggested_stack={
                "backend": "FastAPI",
                "crm": "Salesforce",
                "messaging": "Slack",
                "auth": "OAuth",
            },
            domain="customer-success",
            status="approved",
        )
        brief_kwargs = {
            "readiness_score": 86.0,
            "why_this_now": "External API dependencies must be visible before autonomous build handoff.",
            "merged_product_concept": "An integration contract for Salesforce account sync and Slack renewal notifications.",
            "synthesis_rationale": "Links customer data, API, auth, failure handling, and launch observability requirements.",
            "mvp_scope": ["Salesforce account sync", "Slack renewal webhook notification"],
            "first_milestones": ["Run Salesforce sandbox handoff"],
            "validation_plan": "Run Salesforce sandbox sync and Slack webhook dry run with OAuth scoped tokens.",
            "risks": ["Security and privacy review may delay customer data access."],
            "design_status": "approved",
        }

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Integration Contract Brief",
            domain="customer-success",
            theme="integration-contract",
            lead=Candidate(unit=lead),
            supporting=[],
            source_idea_ids=[lead.id],
            **brief_kwargs,
        )
    )
    return store, brief_id
