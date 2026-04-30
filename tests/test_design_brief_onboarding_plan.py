"""Tests for design brief onboarding plan generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_onboarding_plan import (
    SCHEMA_VERSION,
    build_design_brief_onboarding_plan,
    render_design_brief_onboarding_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_onboarding_plan_translates_persisted_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_onboarding_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.onboarding_plan"
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["target_user"] == "customer operations manager"
    assert report["summary"]["buyer"] == "customer success director"
    assert report["summary"]["workflow_context"] == "approved pilot onboarding"
    assert [phase["id"] for phase in report["onboarding_phases"]] == [
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
    ]
    assert all(
        {"owner", "actions", "exit_criteria", "evidence_reference_ids"} <= set(phase)
        for phase in report["onboarding_phases"]
    )
    assert all(phase["actions"] for phase in report["onboarding_phases"])
    assert [criterion["metric"] for criterion in report["success_criteria"]] == [
        "First value reached",
        "Repeatable enablement",
        "Sponsor acceptance",
        "Evidence continuity",
    ]
    assert [hint["owner"] for hint in report["owner_hints"]] == [
        "Customer success lead",
        "Onboarding specialist",
        "Product lead",
        "Risk owner",
    ]
    assert any("Privacy approval" in risk["risk"] for risk in report["risks"])
    assert [asset["id"] for asset in report["required_assets"]] == ["A1", "A2", "A3", "A4"]
    assert {reference["description"] for reference in report["evidence_references"]} == {
        "sig-onboarding",
        "customers need champion-ready onboarding",
    }
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_build_design_brief_onboarding_plan_is_deterministic(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        first = build_design_brief_onboarding_plan(store, brief_id)
        second = build_design_brief_onboarding_plan(store, brief_id)
    finally:
        store.close()

    assert first == second


def test_render_design_brief_onboarding_plan_markdown_and_json(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_onboarding_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_onboarding_plan(report)

    assert markdown.startswith("# Onboarding Plan: Onboarding Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Onboarding Phases" in markdown
    assert "### phase-1: Account Readiness" in markdown
    assert "### phase-2: Guided First Value" in markdown
    assert "## Success Criteria" in markdown
    assert "- **First value reached**" in markdown
    assert "## Risks" in markdown
    assert "Privacy approval can block customer data setup." in markdown
    assert "## Required Assets" in markdown
    assert "## Evidence References" in markdown

    rendered_json = render_design_brief_onboarding_plan(report, fmt="json")
    assert json.loads(rendered_json) == report
    with pytest.raises(ValueError):
        render_design_brief_onboarding_plan(report, fmt="yaml")


def test_build_design_brief_onboarding_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_onboarding_plan.db"), wal_mode=True)
    try:
        report = build_design_brief_onboarding_plan(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_onboarding_plan.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-onboarding-plan-lead",
        title="Onboarding Plan Lead",
        one_liner="Turn approved pilots into repeatable customer onboarding.",
        category="application",
        problem="Validated ideas stall after pilot approval without onboarding ownership.",
        solution="Export deterministic onboarding plans from design briefs.",
        value_proposition="Make post-sale rollout operational for customer-facing teams.",
        specific_user="customer operations manager",
        buyer="customer success director",
        workflow_context="approved pilot onboarding",
        current_workaround="manual kickoff notes",
        why_now="Pilot approvals need a customer-ready rollout artifact.",
        validation_plan="Track first value, repeat setup, sponsor acceptance, and adoption handoff.",
        first_10_customers="customer success teams managing pilot graduates",
        domain_risks=["Privacy approval can block customer data setup."],
        evidence_signals=["sig-onboarding"],
        inspiring_insights=["customers need champion-ready onboarding"],
        tech_approach="Python export module.",
        suggested_stack={"language": "python"},
        domain="customer-success",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Onboarding Plan Brief",
            domain="customer-success",
            theme="post-sale-onboarding",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=88.0,
            why_this_now="Generated project specs need post-sale onboarding artifacts.",
            merged_product_concept="An onboarding plan export for persisted design briefs.",
            synthesis_rationale="Connects pilot approval to customer rollout operations.",
            mvp_scope=["Onboarding plan JSON", "Onboarding plan Markdown"],
            first_milestones=["Complete guided first-value onboarding"],
            validation_plan="Confirm customer teams can onboard a second user without concierge help.",
            risks=["Privacy approval can block customer data setup."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
