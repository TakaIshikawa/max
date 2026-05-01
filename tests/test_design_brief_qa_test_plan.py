from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_qa_test_plan import (
    KIND,
    SCHEMA_VERSION,
    TEST_SUITE_TYPES,
    build_design_brief_qa_test_plan,
    qa_test_plan_filename,
    render_design_brief_qa_test_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_qa_test_plan_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_rich_brief(tmp_path)
    try:
        report = build_design_brief_qa_test_plan(store, brief_id)
        repeated = build_design_brief_qa_test_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["title"] == "QA Test Plan Brief"
    assert report["design_brief"]["source_idea_ids"] == ["bu-qa-lead", "bu-qa-support"]
    assert report["source_metadata"]["source_idea_count"] == 2
    assert report["summary"]["suite_count"] == len(TEST_SUITE_TYPES)
    assert [suite["coverage_type"] for suite in report["test_suites"]] == list(TEST_SUITE_TYPES)
    assert report["critical_paths"]
    assert report["test_data_needs"]
    assert report["automation_candidates"]
    assert report["manual_review_checks"]
    assert json.loads(json.dumps(report))["schema_version"] == SCHEMA_VERSION


def test_qa_test_plan_rich_source_ideas_drive_traceable_coverage(tmp_path) -> None:
    store, brief_id = _store_with_rich_brief(tmp_path)
    try:
        report = build_design_brief_qa_test_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert any(
        "support triage dashboard" in case
        for suite in report["test_suites"]
        for case in suite["test_cases"]
    )
    assert any("customer support lead" in path["user_journey"] for path in report["critical_paths"])
    assert any("sig-qa-1" == ref["id"] for ref in report["evidence_references"])
    assert any("ins-qa-1" == ref["id"] for ref in report["evidence_references"])
    assert all(suite["source_idea_ids"] == ["bu-qa-lead", "bu-qa-support"] for suite in report["test_suites"])
    assert all(item["source_idea_ids"] for item in report["automation_candidates"])
    assert report["evidence_gaps"] == []


def test_sparse_design_brief_returns_fallbacks_and_evidence_gaps(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_qa_test_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert [suite["coverage_type"] for suite in report["test_suites"]] == list(TEST_SUITE_TYPES)
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "workflow_context",
        "buyer",
        "validation_plan",
        "mvp_scope",
        "risks",
    ]
    gaps = {gap["field"]: gap for gap in report["evidence_gaps"]}
    assert {"mvp_scope", "validation_plan", "risks", "specific_user", "workflow_context", "evidence_references"} <= set(gaps)
    assert gaps["validation_plan"]["severity"] == "high"
    assert any(
        "Evidence gaps are captured" in criterion
        for suite in report["test_suites"]
        for criterion in suite["exit_criteria"]
    )
    assert any(check["check"] == "Evidence gap disposition" for check in report["manual_review_checks"])


def test_markdown_json_invalid_format_and_filename(tmp_path) -> None:
    store, brief_id = _store_with_rich_brief(tmp_path)
    try:
        report = build_design_brief_qa_test_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_qa_test_plan(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_qa_test_plan(report, fmt="markdown")
    assert markdown.startswith("# QA Test Plan: QA Test Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Test Suites" in markdown
    assert "### QAS1: Unit coverage for deterministic artifact logic" in markdown
    assert "### QAS2: Integration coverage for persisted brief workflows" in markdown
    assert "### QAS3: Acceptance coverage for build handoff readiness" in markdown
    assert "### QAS4: Regression coverage for repeated artifact generation" in markdown
    assert "## Critical Paths" in markdown
    assert "## Test Data Needs" in markdown
    assert "## Automation Candidates" in markdown
    assert "## Manual Review Checks" in markdown
    assert "## Evidence Gaps" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    with pytest.raises(ValueError, match="Unsupported QA test plan format: yaml"):
        render_design_brief_qa_test_plan(report, fmt="yaml")

    assert (
        qa_test_plan_filename({"id": "dbf-123", "title": "QA Plan: Alpha / Beta"})
        == "dbf-123-QA-Plan-Alpha-Beta-qa-test-plan.md"
    )
    assert (
        qa_test_plan_filename({"id": "dbf-123", "title": "QA Plan: Alpha / Beta"}, fmt="json")
        == "dbf-123-QA-Plan-Alpha-Beta-qa-test-plan.json"
    )


def test_build_design_brief_qa_test_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_qa_test_plan.db"), wal_mode=True)
    try:
        report = build_design_brief_qa_test_plan(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_rich_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_qa_test_plan.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-qa-lead",
        title="QA Plan Lead",
        one_liner="Generate build handoff QA plans from design briefs.",
        category="application",
        problem="Autonomous implementation needs executable validation guidance.",
        solution="Create deterministic QA suites, critical paths, test data needs, and evidence gaps.",
        value_proposition="Make implementation handoff testable before build starts.",
        specific_user="customer support lead",
        buyer="VP of Support",
        workflow_context="support triage dashboard",
        current_workaround="manual QA checklist",
        why_now="Generated specs need validation plans before autonomous execution.",
        validation_plan="Run seeded fixture tests and owner acceptance review before implementation.",
        first_10_customers="support teams with weekly triage reviews",
        domain_risks=["Regression coverage may miss escalated ticket routing failures."],
        evidence_signals=["sig-qa-1"],
        inspiring_insights=["ins-qa-1"],
        tech_approach="Deterministic Python artifact over persisted design brief fields.",
        domain="support-ops",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-qa-support",
        title="QA Plan Support",
        one_liner="Trace QA coverage to linked product ideas.",
        category="application",
        problem="Teams skip sparse-data and regression scenarios during handoff.",
        solution="Include automation candidates, manual reviews, and test data needs.",
        value_proposition="Reduce missed coverage in implementation plans.",
        specific_user="QA engineer",
        buyer="support operations director",
        workflow_context="ticket escalation workflow",
        validation_plan="Compare Markdown and JSON output for deterministic QA sections.",
        domain_risks=["Integration tests need realistic ticket status fixtures."],
        evidence_signals=["sig-qa-2"],
        domain="support-ops",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="QA Test Plan Brief",
            domain="support-ops",
            theme="qa-test-plan",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=82.0,
            why_this_now="Generated specs need executable validation guidance before autonomous implementation.",
            merged_product_concept="A QA test plan artifact for design brief handoff.",
            synthesis_rationale="Combines source idea risks with validation and regression coverage.",
            mvp_scope=["support triage dashboard", "Markdown QA handoff export"],
            first_milestones=["Generate QA suites from persisted brief"],
            validation_plan="Run seeded fixture tests and owner acceptance review before implementation.",
            risks=[
                "Regression coverage may miss escalated ticket routing failures.",
                "Integration tests need realistic ticket status fixtures.",
            ],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_qa_test_plan.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-qa-sparse",
        title="Sparse QA Lead",
        one_liner="Create QA defaults with weak context.",
        category="application",
        problem="QA handoff inputs are incomplete.",
        solution="Use conservative coverage and evidence gaps.",
        value_proposition="Keep validation planning moving.",
        domain="support-ops",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse QA Brief",
            domain="support-ops",
            theme="qa-test-plan",
            lead=Candidate(unit=lead),
            readiness_score=35.0,
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
