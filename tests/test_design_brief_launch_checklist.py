"""Tests for design brief launch checklist generation."""

from __future__ import annotations

import json

from max.analysis.design_brief_launch_checklist import (
    SCHEMA_VERSION,
    build_design_brief_launch_checklist,
    render_design_brief_launch_checklist,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_launch_checklist_sections_and_traceability(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_launch_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    assert checklist["schema_version"] == SCHEMA_VERSION
    assert checklist["kind"] == "max.design_brief.launch_checklist"
    assert checklist["design_brief"]["id"] == brief_id
    assert checklist["summary"]["launch_gate"] == "ready_for_launch_review"
    assert [section["id"] for section in checklist["sections"]] == [
        "readiness",
        "instrumentation",
        "validation",
        "rollout",
        "follow_up",
    ]
    assert [item["id"] for item in checklist["checklist_items"]] == [
        f"DBLC{index}" for index in range(1, 16)
    ]
    assert all(item["source_idea_ids"] for item in checklist["checklist_items"])
    assert any(
        item["section_id"] == "readiness" and "risk" in item["task"].lower()
        for item in checklist["checklist_items"]
    )
    assert json.loads(json.dumps(checklist))["design_brief"]["id"] == brief_id


def test_render_design_brief_launch_checklist_markdown(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_launch_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    markdown = render_design_brief_launch_checklist(checklist, fmt="markdown")

    assert markdown.startswith("# Launch Checklist: Launch Checklist Brief")
    assert "## Readiness" in markdown
    assert "## Instrumentation" in markdown
    assert "## Validation" in markdown
    assert "## Rollout" in markdown
    assert "## Follow-up" in markdown
    assert "### DBLC1: Confirm launch scope from the persisted MVP scope." in markdown
    assert "- Exit criteria: MVP scope and explicit non-goals are approved for execution." in markdown
    assert f"Design brief: `{brief_id}`" in markdown


def test_build_design_brief_launch_checklist_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_launch_checklist.db"), wal_mode=True)
    try:
        checklist = build_design_brief_launch_checklist(store, "dbf-missing")
    finally:
        store.close()

    assert checklist is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_launch_checklist.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-launch-brief-lead",
        title="Launch Checklist Lead",
        one_liner="Prepare launch readiness from persisted design briefs.",
        category="application",
        problem="Execution teams need a readiness handoff.",
        solution="Generate a deterministic launch checklist from the design brief.",
        value_proposition="Make launch readiness explicit before execution.",
        specific_user="release owner",
        buyer="engineering manager",
        workflow_context="design-to-execution handoff",
        current_workaround="manual launch notes",
        why_now="Design briefs already persist execution context.",
        validation_plan="Review checklist with product, engineering, and support.",
        first_10_customers="internal release owners",
        domain_risks=["Launch owners may miss unresolved validation gaps."],
        tech_approach="FastAPI route using deterministic analysis code.",
        suggested_stack={"language": "python", "framework": "fastapi"},
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-launch-brief-support",
        title="Launch Checklist Support",
        one_liner="Track instrumentation and follow-up for launch readiness.",
        category="application",
        problem="Teams lose source traceability after launch.",
        solution="Attach source idea IDs to checklist items.",
        value_proposition="Preserve evidence across handoffs.",
        specific_user="product operator",
        buyer="product lead",
        workflow_context="post-launch review",
        validation_plan="Compare JSON and Markdown output.",
        domain_risks=["Traceability can drift from source ideas."],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Launch Checklist Brief",
            domain="developer-tools",
            theme="launch-readiness",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=86.0,
            why_this_now="Launch readiness is the next design brief handoff.",
            merged_product_concept="A launch checklist export for persisted design briefs.",
            synthesis_rationale="Completes execution handoff artifacts.",
            mvp_scope=["JSON launch checklist", "Markdown launch checklist"],
            first_milestones=["Return launch checklist JSON", "Return launch checklist Markdown"],
            validation_plan="Confirm JSON and Markdown preserve source idea traceability.",
            risks=["Launch checklist may be treated as a substitute for validation."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id
