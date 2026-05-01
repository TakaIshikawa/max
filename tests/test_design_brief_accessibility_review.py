from __future__ import annotations

import json

import pytest

from max.analysis import build_design_brief_accessibility_review as exported_build
from max.analysis import render_design_brief_accessibility_review as exported_render
from max.analysis.design_brief_accessibility_review import (
    KIND,
    SCHEMA_VERSION,
    accessibility_review_filename,
    build_design_brief_accessibility_review,
    render_design_brief_accessibility_review,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_accessibility_review_is_stable_and_complete(tmp_path) -> None:
    store, brief_id = _store_with_accessibility_brief(tmp_path)
    try:
        first = build_design_brief_accessibility_review(store, brief_id)
        second = build_design_brief_accessibility_review(store, brief_id)
    finally:
        store.close()

    assert first is not None
    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == KIND
    assert first["design_brief"]["id"] == brief_id
    assert first["design_brief"]["source_idea_ids"] == ["bu-a11y-lead", "bu-a11y-support"]
    assert first["summary"]["review_gate"] == "accessibility_review_required"
    assert first["summary"]["affected_user_group_count"] >= 3
    assert first["summary"]["wcag_check_count"] == 4
    assert first["summary"]["validation_task_count"] == 4
    assert first["summary"]["fallbacks_used"] == []

    user_group_ids = [group["id"] for group in first["affected_user_groups"]]
    assert ["visual", "motor", "cognitive", "hearing"] == user_group_ids
    assert any(risk["severity"] == "high" for risk in first["accessibility_risks"])
    assert any("2.1.1" in check["wcag_refs"] for check in first["wcag_oriented_checks"])
    assert all(task["source_idea_ids"] == ["bu-a11y-lead", "bu-a11y-support"] for task in first["validation_tasks"])
    assert any(ref["id"] == "sig-a11y-1" for ref in first["evidence_references"])
    assert all(owner["role"] for owner in first["owners"])
    assert json.loads(json.dumps(first))["schema_version"] == SCHEMA_VERSION


def test_sparse_design_brief_has_conservative_accessibility_tasks(tmp_path) -> None:
    store, brief_id = _store_with_sparse_accessibility_brief(tmp_path)
    try:
        report = build_design_brief_accessibility_review(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["review_gate"] == "needs_accessibility_discovery"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "validation_plan",
        "mvp_scope",
        "risks",
    ]
    assert [group["id"] for group in report["affected_user_groups"]] == ["visual", "motor", "cognitive"]
    assert any(risk["title"] == "Accessibility acceptance criteria are under-specified" for risk in report["accessibility_risks"])
    assert any(task["task"] == "Accessibility acceptance criteria disposition" for task in report["validation_tasks"])
    assert all(task["priority"] == "high" for task in report["validation_tasks"] if task["id"] in {"AVT3", "AVT4"})


def test_render_design_brief_accessibility_review_json_and_markdown_match_content(tmp_path) -> None:
    store, brief_id = _store_with_accessibility_brief(tmp_path)
    try:
        report = build_design_brief_accessibility_review(store, brief_id)
    finally:
        store.close()

    assert report is not None
    parsed = json.loads(render_design_brief_accessibility_review(report, "json"))
    assert parsed == report
    assert parsed["accessibility_risks"][0]["title"] in render_design_brief_accessibility_review(report, "markdown")

    markdown = render_design_brief_accessibility_review(report, "markdown")
    assert markdown.startswith("# Accessibility Review: Accessible Support Triage Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Design Brief Summary" in markdown
    assert "## Affected User Groups" in markdown
    assert "## Accessibility Risks" in markdown
    assert "## WCAG-Oriented Checks" in markdown
    assert "## Inclusive Design Opportunities" in markdown
    assert "## Validation Tasks" in markdown
    assert "## Evidence References" in markdown
    assert "WCAG1 perceivable" in markdown
    assert "sig-a11y-1" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    with pytest.raises(ValueError, match="Unsupported accessibility review format: yaml"):
        render_design_brief_accessibility_review(report, "yaml")


def test_accessibility_review_filename() -> None:
    brief = {"id": "dbf-123", "title": "A11y Review: Alpha / Beta"}
    assert accessibility_review_filename(brief) == "dbf-123-A11y-Review-Alpha-Beta-accessibility-review.json"
    assert accessibility_review_filename(brief, fmt="markdown") == "dbf-123-A11y-Review-Alpha-Beta-accessibility-review.md"


def test_build_design_brief_accessibility_review_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_accessibility_review.db"), wal_mode=True)
    try:
        assert build_design_brief_accessibility_review(store, "dbf-missing") is None
    finally:
        store.close()


def test_design_brief_accessibility_review_is_importable_from_analysis_package(tmp_path) -> None:
    store, brief_id = _store_with_accessibility_brief(tmp_path)
    try:
        report = exported_build(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = exported_render(report, fmt="markdown")
    assert markdown.startswith("# Accessibility Review: Accessible Support Triage Brief")


def _store_with_accessibility_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_accessibility_review.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-a11y-lead",
        title="Accessible Support Triage",
        one_liner="Create accessible review dashboards for support teams.",
        category="application",
        problem="Support teams use visual status dashboards that can miss screen reader and keyboard users.",
        solution="Generate a semantic support triage dashboard with keyboard workflows and visible focus states.",
        value_proposition="Reduce support risk by making review and approval workflows accessible before build.",
        specific_user="support operations analyst",
        buyer="VP of Support",
        workflow_context="support triage dashboard with approval queue, video notes, and status summaries",
        current_workaround="manual spreadsheet review",
        why_now="Generated specs need an accessibility review before autonomous implementation.",
        validation_plan="Run keyboard, screen reader, contrast, and caption checks before implementation.",
        domain_risks=[
            "Visual status colors may hide priority from screen reader users.",
            "Keyboard focus may be lost during generated recommendation review.",
        ],
        evidence_signals=["sig-a11y-1"],
        inspiring_insights=["ins-a11y-1"],
        tech_approach="Deterministic Python artifact over persisted design brief fields.",
        domain="support-ops",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-a11y-support",
        title="Accessible Validation Support",
        one_liner="Trace WCAG checks to source ideas.",
        category="application",
        problem="Teams forget captions, transcripts, and keyboard-only validation for handoff artifacts.",
        solution="Add WCAG-oriented checks, owners, and validation tasks.",
        value_proposition="Catch accessibility blockers before implementation handoff.",
        specific_user="QA engineer",
        buyer="support operations director",
        workflow_context="ticket escalation workflow with meeting recordings",
        validation_plan="Compare Markdown and JSON accessibility content for deterministic parity.",
        domain_risks=["Accessibility acceptance criteria may be under-specified."],
        evidence_signals=["sig-a11y-2"],
        domain="support-ops",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Accessible Support Triage Brief",
            domain="support-ops",
            theme="accessibility-review",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=84.0,
            why_this_now="Generated specs need accessibility gates before autonomous builders start implementation.",
            merged_product_concept="An accessible support triage dashboard with generated summaries and approval workflows.",
            synthesis_rationale="Combines visual dashboard, keyboard workflow, and caption validation risks.",
            mvp_scope=["support triage dashboard", "keyboard approval queue", "video note transcript review"],
            first_milestones=["Map keyboard path", "Validate screen reader status messages"],
            validation_plan="Run keyboard, screen reader, contrast, caption, and cognitive-load reviews before implementation.",
            risks=[
                "Visual status colors may hide priority from screen reader users.",
                "Keyboard focus may be lost during generated recommendation review.",
            ],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_accessibility_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_accessibility_review.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-a11y-sparse",
        title="Sparse Accessibility Lead",
        one_liner="Create accessibility defaults with weak context.",
        category="application",
        problem="Accessibility handoff inputs are incomplete.",
        solution="Use conservative WCAG checks and validation tasks.",
        value_proposition="Keep accessibility review moving.",
        domain="support-ops",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Accessibility Brief",
            domain="support-ops",
            theme="accessibility-review",
            lead=Candidate(unit=lead),
            readiness_score=30.0,
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
