"""Tests for design brief dependency risk map generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis import build_design_brief_dependency_risk_map as exported_build
from max.analysis import render_design_brief_dependency_risk_map as exported_render
from max.analysis.design_brief_dependency_risk_map import (
    KIND,
    CSV_COLUMNS,
    RISK_CATEGORIES,
    SCHEMA_VERSION,
    build_design_brief_dependency_risk_map,
    dependency_risk_map_filename,
    render_design_brief_dependency_risk_map,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_dependency_risk_map_representative_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_dependency_risk_map(store, brief_id)
        repeated = build_design_brief_dependency_risk_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["risk_count"] == 5
    assert report["summary"]["category_count"] == 5
    assert [risk["id"] for risk in report["dependency_risks"]] == [
        "DBDR1",
        "DBDR2",
        "DBDR3",
        "DBDR4",
        "DBDR5",
    ]
    assert [risk["risk_category"] for risk in report["dependency_risks"]] == list(RISK_CATEGORIES)
    assert report["dependency_risks"][0]["dependency_name"] == "Salesforce, Slack, OAuth or SSO provider"
    assert report["dependency_risks"][0]["severity"] == "high"
    assert report["dependency_risks"][0]["owner"] == "Engineering owner"
    assert "sandbox access" in report["dependency_risks"][0]["mitigation"]
    assert report["dependency_risks"][0]["evidence_reference_id"] == "design_brief.merged_product_concept"
    assert report["dependency_risks"][2]["risk_category"] == "compliance dependency"
    assert report["dependency_risks"][2]["severity"] == "high"
    assert {reference["id"] for reference in report["evidence_references"]} >= {
        "design_brief.merged_product_concept",
        "design_brief.risks",
        "sig-dependency-risk",
        "ins-dependency-risk",
    }
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_build_design_brief_dependency_risk_map_sparse_inputs(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_dependency_risk_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["risk_count"] == 5
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
    ]
    assert report["dependency_context"]["detected_vendors"] == []
    assert report["dependency_risks"][0]["dependency_name"] == "External API or vendor service"
    assert report["dependency_risks"][0]["severity"] == "medium"
    assert report["dependency_risks"][3]["risk_category"] == "staffing dependency"
    assert report["dependency_risks"][3]["severity"] == "high"
    assert report["dependency_risks"][4]["severity"] == "high"


def test_render_design_brief_dependency_risk_map_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_dependency_risk_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_dependency_risk_map(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_dependency_risk_map(report, fmt="markdown")
    assert markdown.startswith("# Dependency Risk Map: Dependency Risk Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Dependency Risks" in markdown
    assert "### DBDR1: Salesforce, Slack, OAuth or SSO provider" in markdown
    assert "- Risk category: vendor/API dependency" in markdown
    assert "- Severity: high" in markdown
    assert "- Owner: Engineering owner" in markdown
    assert "- Mitigation: Confirm sandbox access" in markdown
    assert "- Evidence reference: design_brief.merged_product_concept" in markdown
    assert "## Evidence References" in markdown

    csv_text = render_design_brief_dependency_risk_map(report, fmt="csv")
    reader = csv.DictReader(StringIO(csv_text))
    rows = list(reader)
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert len(rows) == 5
    assert rows[0] == {
        "design_brief_id": brief_id,
        "dependency_id": "DBDR1",
        "dependency_name": "Salesforce, Slack, OAuth or SSO provider",
        "category": "vendor/API dependency",
        "owner": "Engineering owner",
        "risk_level": "high",
        "impacted_workstreams": "merged_product_concept; mvp_scope; tech_approach; suggested_stack",
        "evidence_ids": "design_brief.merged_product_concept",
        "mitigation": report["dependency_risks"][0]["mitigation"],
        "next_action": (
            "Engineering owner to validate dependency assumptions for "
            "Salesforce, Slack, OAuth or SSO provider."
        ),
    }
    assert '"Salesforce, Slack, OAuth or SSO provider"' in csv_text

    with pytest.raises(ValueError, match="Unsupported dependency risk map format: yaml"):
        render_design_brief_dependency_risk_map(report, fmt="yaml")


def test_render_design_brief_dependency_risk_map_csv_escapes_special_values(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_dependency_risk_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["dependency_risks"][0]["dependency_name"] = 'CRM, "enterprise"\nworkflow'
    report["dependency_risks"][0]["source_fields"] = [
        "merged_product_concept",
        'customer, "success"',
        "validation\nplan",
    ]
    report["dependency_risks"][0]["evidence_reference_id"] = 'evidence, "alpha"'

    csv_text = render_design_brief_dependency_risk_map(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert rows[0]["dependency_name"] == 'CRM, "enterprise"\nworkflow'
    assert rows[0]["impacted_workstreams"] == (
        'merged_product_concept; customer, "success"; validation\nplan'
    )
    assert rows[0]["evidence_ids"] == 'evidence, "alpha"'
    assert '"CRM, ""enterprise""\nworkflow"' in csv_text
    assert '"merged_product_concept; customer, ""success""; validation\nplan"' in csv_text
    assert '"evidence, ""alpha"""' in csv_text


def test_render_design_brief_dependency_risk_map_csv_sparse_inputs(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_dependency_risk_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_dependency_risk_map(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert len(rows) == 5
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[0]["dependency_name"] == "External API or vendor service"
    assert rows[0]["risk_level"] == "medium"
    assert rows[3]["category"] == "staffing dependency"
    assert rows[3]["risk_level"] == "high"


def test_design_brief_dependency_risk_map_empty_store_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_dependency_risk_map.db"), wal_mode=True)
    try:
        report = build_design_brief_dependency_risk_map(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def test_dependency_risk_map_filename_uses_brief_id_and_title() -> None:
    brief = {"id": "dbf-risk001", "title": "Dependency Risk: Alpha / Beta"}

    assert (
        dependency_risk_map_filename(brief)
        == "dbf-risk001-Dependency-Risk-Alpha-Beta-dependency-risk-map.md"
    )
    assert (
        dependency_risk_map_filename(brief, fmt="json")
        == "dbf-risk001-Dependency-Risk-Alpha-Beta-dependency-risk-map.json"
    )
    assert (
        dependency_risk_map_filename(brief, fmt="csv")
        == "dbf-risk001-Dependency-Risk-Alpha-Beta-dependency-risk-map.csv"
    )


def test_design_brief_dependency_risk_map_is_importable_from_analysis_package(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = exported_build(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert exported_render(report).startswith("# Dependency Risk Map: Dependency Risk Brief")


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_dependency_risk_map_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-dependency-risk-sparse",
            title="Sparse Dependency Risk Lead",
            one_liner="Sparse source for dependency risk maps.",
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
            id="bu-dependency-risk-lead",
            title="Dependency Risk Lead",
            one_liner="Map external dependencies before implementation handoff.",
            category="application",
            problem="Autonomous builders miss Salesforce, Slack, and customer data readiness risks.",
            solution="Generate a dependency risk map covering APIs, data, compliance, staffing, and launch.",
            value_proposition="Make execution risks traceable before handoff.",
            specific_user="customer success operator",
            buyer="customer success director",
            workflow_context="Salesforce to Slack renewal workflow",
            current_workaround="Manual Salesforce exports and Slack pings",
            why_now="Generated project specs increasingly depend on external APIs.",
            validation_plan="Run Salesforce sandbox sync and Slack notification dry run.",
            first_10_customers="customer success teams using Salesforce",
            domain_risks=[
                "OAuth scopes and customer data retention need security and privacy review.",
            ],
            evidence_signals=["sig-dependency-risk"],
            inspiring_insights=["ins-dependency-risk"],
            tech_approach="FastAPI webhook API with Salesforce, Slack, OAuth, and Postgres.",
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
            "readiness_score": 88.0,
            "why_this_now": "External API dependencies must be visible before autonomous build handoff.",
            "merged_product_concept": "A dependency risk map for Salesforce and Slack workflow handoffs.",
            "synthesis_rationale": "Links customer data, API, compliance, staffing, and launch risks.",
            "mvp_scope": ["Salesforce account sync", "Slack renewal notification"],
            "first_milestones": ["Run Salesforce sandbox handoff"],
            "validation_plan": "Run Salesforce sandbox sync and Slack notification dry run.",
            "risks": ["Security and privacy review may delay customer data access."],
            "design_status": "approved",
        }

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Dependency Risk Brief",
            domain="customer-success",
            theme="dependency-risk",
            lead=Candidate(unit=lead),
            supporting=[],
            source_idea_ids=[lead.id],
            **brief_kwargs,
        )
    )
    return store, brief_id
