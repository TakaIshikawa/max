from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_work_breakdown import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_work_breakdown,
    render_design_brief_work_breakdown,
    work_breakdown_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_work_breakdown_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_rich_brief(tmp_path)
    try:
        report = build_design_brief_work_breakdown(store, brief_id)
        repeated = build_design_brief_work_breakdown(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["title"] == "Work Breakdown Brief"
    assert report["design_brief"]["source_idea_ids"] == ["bu-wb-lead", "bu-wb-support"]
    assert report["summary"] == {
        "epic_count": 4,
        "task_count": 8,
        "dependency_count": 8,
        "owner_count": 4,
        "acceptance_check_count": 6,
        "sequencing_risk_count": 3,
        "gap_count": 0,
        "next_action_count": 3,
        "fallbacks_used": [],
        "implementation_gate": "ready_for_execution_planning",
    }
    assert [epic["id"] for epic in report["epics"]] == ["WBE1", "WBE2", "WBE3", "WBE4"]
    assert [task["id"] for task in report["tasks"]] == [
        "WBT1",
        "WBT2",
        "WBT3",
        "WBT4",
        "WBT5",
        "WBT6",
        "WBT7",
        "WBT8",
    ]
    assert [check["id"] for check in report["acceptance_checks"]] == [
        "WBAC1",
        "WBAC2",
        "WBAC3",
        "WBAC4",
        "WBAC5",
        "WBAC6",
    ]
    assert report["tasks"][0]["depends_on"] == []
    assert report["tasks"][4]["depends_on"] == ["WBT3", "WBT4"]
    assert all(task["owner"] for task in report["tasks"])
    assert all(task["acceptance_check_ids"] for task in report["tasks"])
    assert json.loads(json.dumps(report))["schema_version"] == SCHEMA_VERSION


def test_rich_source_ideas_drive_execution_context_and_traceability(tmp_path) -> None:
    store, brief_id = _store_with_rich_brief(tmp_path)
    try:
        report = build_design_brief_work_breakdown(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["work_context"]["specific_user"] == "implementation lead"
    assert report["work_context"]["buyer"] == "VP of Product"
    assert report["work_context"]["workflow_context"] == "autonomous implementation handoff"
    assert report["work_context"]["primary_scope"] == "work breakdown JSON artifact"
    assert any(
        "autonomous implementation handoff" in task["description"]
        for task in report["tasks"]
    )
    assert all(task["source_idea_ids"] == ["bu-wb-lead", "bu-wb-support"] for task in report["tasks"])
    assert all(check["source_idea_ids"] == ["bu-wb-lead", "bu-wb-support"] for check in report["acceptance_checks"])
    assert any("Sequencing can hide dependency risks" in risk["risk"] for risk in report["sequencing_risks"])
    assert report["gaps"] == []


def test_sparse_design_brief_returns_gaps_and_next_actions(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_work_breakdown(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["implementation_gate"] == "resolve_gaps_first"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
        "risks",
    ]
    gap_fields = {gap["field"] for gap in report["gaps"]}
    assert {
        "specific_user",
        "buyer",
        "workflow_context",
        "merged_product_concept",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
        "risks",
    } <= gap_fields
    assert report["dependencies"][0]["id"] == "WBD0"
    assert report["dependencies"][0]["from_task_id"] == "gaps"
    assert report["tasks"][0]["status"] == "blocked_until_gap_review"
    assert {task["status"] for task in report["tasks"][1:]} == {"planned_after_gap_review"}
    assert report["next_actions"][0]["related_gap_ids"] == [gap["id"] for gap in report["gaps"]]
    assert any(risk["id"] == "WBSR4" for risk in report["sequencing_risks"])


def test_markdown_json_invalid_format_and_filename(tmp_path) -> None:
    store, brief_id = _store_with_rich_brief(tmp_path)
    try:
        report = build_design_brief_work_breakdown(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_work_breakdown(report, fmt="json")
    assert json.loads(rendered_json) == report
    assert rendered_json == render_design_brief_work_breakdown(report, fmt="json")

    markdown = render_design_brief_work_breakdown(report, fmt="markdown")
    assert markdown.startswith("# Work Breakdown: Work Breakdown Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Context" in markdown
    assert "## Epics" in markdown
    assert "### WBE1: Execution Foundation" in markdown
    assert "### WBE2: Core Workflow Build" in markdown
    assert "## Dependencies" in markdown
    assert "## Owners" in markdown
    assert "## Acceptance Checks" in markdown
    assert "## Sequencing Risks" in markdown
    assert "## Gaps" in markdown
    assert "## Next Actions" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    with pytest.raises(ValueError, match="Unsupported work breakdown format: yaml"):
        render_design_brief_work_breakdown(report, fmt="yaml")

    assert (
        work_breakdown_filename({"id": "dbf-123", "title": "Build Plan: Alpha / Beta"})
        == "dbf-123-Build-Plan-Alpha-Beta-work-breakdown.md"
    )
    assert (
        work_breakdown_filename({"id": "dbf-123", "title": "Build Plan: Alpha / Beta"}, fmt="json")
        == "dbf-123-Build-Plan-Alpha-Beta-work-breakdown.json"
    )


def test_build_design_brief_work_breakdown_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_work_breakdown.db"), wal_mode=True)
    try:
        report = build_design_brief_work_breakdown(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_rich_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_work_breakdown.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-wb-lead",
        title="Work Breakdown Lead",
        one_liner="Generate implementation-ready work breakdowns from design briefs.",
        category="application",
        problem="Autonomous coding agents receive strategy artifacts without execution slices.",
        solution="Create epics, tasks, dependencies, owners, acceptance checks, risks, gaps, and next actions.",
        value_proposition="Make design brief handoff executable before implementation starts.",
        specific_user="implementation lead",
        buyer="VP of Product",
        workflow_context="autonomous implementation handoff",
        current_workaround="manual decomposition spreadsheet",
        why_now="Design brief artifacts are ready for agent execution planning.",
        validation_plan="Run seeded fixture tests and product owner acceptance review.",
        first_10_customers="product teams using autonomous implementation agents",
        domain_risks=["Sequencing can hide dependency risks between scope and validation."],
        evidence_signals=["sig-wb-1"],
        inspiring_insights=["ins-wb-1"],
        tech_approach="Deterministic Python artifact over persisted design brief records.",
        domain="developer-tools",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-wb-support",
        title="Work Breakdown Support",
        one_liner="Trace execution tasks back to source ideas.",
        category="application",
        problem="Teams lose ownership and acceptance criteria during implementation handoff.",
        solution="Include owners, dependencies, and acceptance checks for every implementation phase.",
        value_proposition="Reduce ambiguity in agent execution plans.",
        specific_user="engineering manager",
        buyer="product operations director",
        workflow_context="implementation readiness review",
        validation_plan="Compare deterministic Markdown and JSON work breakdown output.",
        domain_risks=["Sparse briefs can create misleading task certainty."],
        evidence_signals=["sig-wb-2"],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Work Breakdown Brief",
            domain="developer-tools",
            theme="work-breakdown",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=86.0,
            why_this_now="Design brief artifacts need execution-ready decomposition.",
            merged_product_concept="A deterministic work breakdown artifact for autonomous implementation agents.",
            synthesis_rationale="Source ideas show that strategy artifacts need task sequencing.",
            mvp_scope=["work breakdown JSON artifact", "Markdown work breakdown export"],
            first_milestones=["Generate epics and dependencies", "Validate rendering determinism"],
            validation_plan="Run seeded fixture tests and product owner acceptance review.",
            risks=[
                "Sequencing can hide dependency risks between scope and validation.",
                "Sparse briefs can create misleading task certainty.",
            ],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_work_breakdown.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-wb-sparse",
        title="Sparse Work Breakdown Lead",
        one_liner="Create work breakdown defaults with weak context.",
        category="application",
        problem="Execution inputs are incomplete.",
        solution="Use conservative tasks and explicit gaps.",
        value_proposition="Keep handoff planning moving.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Work Breakdown Brief",
            domain="developer-tools",
            theme="work-breakdown",
            lead=Candidate(unit=lead),
            readiness_score=31.0,
            why_this_now="",
            merged_product_concept="",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
    return store, brief_id
