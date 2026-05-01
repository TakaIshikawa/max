"""Tests for design brief customer journey map generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_customer_journey_map import (
    SCHEMA_VERSION,
    build_design_brief_customer_journey_map,
    render_design_brief_customer_journey_map,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_customer_journey_map_translates_persisted_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_journey_map(store, brief_id)
        repeated = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.customer_journey_map"
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["target_user"] == "customer operations manager"
    assert report["summary"]["buyer"] == "customer success director"
    assert report["summary"]["workflow_context"] == "approved pilot onboarding"
    assert report["summary"]["current_workaround"] == "manual kickoff notes"
    assert report["summary"]["fallbacks_used"] == []
    assert [stage["id"] for stage in report["journey_stages"]] == [
        "JM1",
        "JM2",
        "JM3",
        "JM4",
        "JM5",
    ]
    assert [stage["name"] for stage in report["journey_stages"]] == [
        "Problem Awareness",
        "Solution Evaluation",
        "First Use",
        "Repeat Adoption",
        "Expansion Decision",
    ]
    assert all(
        {
            "user_goals",
            "touchpoints",
            "friction_points",
            "success_signals",
            "owner",
            "source_idea_ids",
        }
        <= set(stage)
        for stage in report["journey_stages"]
    )
    assert all(stage["source_idea_ids"] == ["bu-journey-lead", "bu-journey-support"] for stage in report["journey_stages"])
    assert report["journey_stages"][0]["owner"] == "Product marketing owner"
    assert "design_brief.why_this_now" in report["journey_stages"][0]["evidence_reference_ids"]
    assert any("Privacy approval" in point for point in report["journey_stages"][2]["friction_points"])
    assert {reference["id"] for reference in report["evidence_references"]} >= {
        "design_brief.why_this_now",
        "design_brief.synthesis_rationale",
        "design_brief.validation_plan",
        "sig-journey",
        "ins-journey",
        "sig-support",
    }
    assert report["readiness_warnings"] == []
    assert [idea["id"] for idea in report["source_ideas"]] == ["bu-journey-lead", "bu-journey-support"]
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_build_design_brief_customer_journey_map_sparse_brief_uses_fallbacks(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "design_brief_customer_journey_map_sparse.db"), wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-journey-sparse",
            title="Sparse Journey Source",
            one_liner="Sparse source idea for fallback journey mapping.",
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
                title="Sparse Journey Brief",
                domain="",
                theme="",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=44.0,
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
        report = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["target_user"] == "Sparse Journey Brief user"
    assert report["summary"]["buyer"] == "customer sponsor"
    assert report["summary"]["workflow_context"] == "Sparse Journey Brief workflow"
    assert report["summary"]["current_workaround"] == "manual or ad hoc workflow"
    assert report["summary"]["value_proposition"] == (
        "Help Sparse Journey Brief user improve Sparse Journey Brief workflow."
    )
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "current_workaround",
        "value_proposition",
    ]
    assert report["journey_stages"][0]["source_idea_ids"] == ["bu-journey-sparse"]
    assert report["journey_stages"][0]["user_goals"]
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


def test_render_design_brief_customer_journey_map_markdown_json_and_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_customer_journey_map(report, fmt="markdown")
    assert markdown.startswith("# Customer Journey Map: Customer Journey Map Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Journey Context" in markdown
    assert "## Journey Stages" in markdown
    assert "### 1. Problem Awareness" in markdown
    assert "### 3. First Use" in markdown
    assert "- User goals:" in markdown
    assert "- Touchpoints:" in markdown
    assert "- Friction points:" in markdown
    assert "- Success signals:" in markdown
    assert "## Evidence References" in markdown
    assert "**sig-journey**" in markdown
    assert "## Readiness Warnings" in markdown

    rendered_json = render_design_brief_customer_journey_map(report, fmt="json")
    assert json.loads(rendered_json) == report

    with pytest.raises(ValueError, match="Unsupported customer journey map format: yaml"):
        render_design_brief_customer_journey_map(report, fmt="yaml")


def test_build_design_brief_customer_journey_map_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_customer_journey_map.db"), wal_mode=True)
    try:
        report = build_design_brief_customer_journey_map(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_customer_journey_map.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-journey-lead",
        title="Journey Map Lead",
        one_liner="Turn approved pilots into traceable adoption journeys.",
        category="application",
        problem="Validated ideas lack a user adoption path after design brief approval.",
        solution="Export deterministic customer journey maps from design briefs.",
        value_proposition="Make adoption planning concrete for customer-facing teams.",
        specific_user="customer operations manager",
        buyer="customer success director",
        workflow_context="approved pilot onboarding",
        current_workaround="manual kickoff notes",
        why_now="Pilot approvals need customer journey planning before rollout.",
        validation_plan="Track first value, repeat usage, sponsor acceptance, and expansion readiness.",
        first_10_customers="customer success teams managing pilot graduates",
        domain_risks=["Privacy approval can block customer data setup."],
        evidence_signals=["sig-journey"],
        inspiring_insights=["ins-journey"],
        tech_approach="Python export module.",
        suggested_stack={"language": "python"},
        domain="customer-success",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-journey-support",
        title="Journey Map Support",
        one_liner="Capture repeat adoption touchpoints for pilot customers.",
        category="application",
        problem="Teams stop after first use without repeat adoption evidence.",
        solution="Add journey stages with touchpoints and success signals.",
        value_proposition="Help teams understand adoption friction after first use.",
        specific_user="customer champion",
        buyer="product lead",
        workflow_context="repeat pilot rollout",
        current_workaround="ad hoc follow-up emails",
        validation_plan="Confirm repeat usage and support handoff.",
        domain_risks=["Champion handoff may not happen before expansion review."],
        evidence_signals=["sig-support"],
        domain="customer-success",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Customer Journey Map Brief",
            domain="customer-success",
            theme="adoption-planning",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=88.0,
            why_this_now="Generated project specs need customer journey artifacts.",
            merged_product_concept="A customer journey map export for persisted design briefs.",
            synthesis_rationale="Connects pilot approval to adoption planning and expansion decisions.",
            mvp_scope=["Journey map JSON", "Journey map Markdown"],
            first_milestones=["Complete guided first-value journey"],
            validation_plan="Confirm customer teams can repeat the workflow without concierge help.",
            risks=["Privacy approval can block customer data setup."],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )
    return store, brief_id
