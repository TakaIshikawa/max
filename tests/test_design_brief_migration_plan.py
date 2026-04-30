"""Tests for design brief migration plan generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_migration_plan import (
    KIND,
    PHASES,
    SCHEMA_VERSION,
    build_design_brief_migration_plan,
    migration_plan_filename,
    render_design_brief_migration_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_migration_plan_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_migration_plan(store, brief_id)
        repeated = build_design_brief_migration_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["title"] == "Migration Plan Brief"
    assert report["design_brief"]["source_idea_ids"] == [
        "bu-migration-lead",
        "bu-migration-support",
    ]
    assert report["summary"]["phase_count"] == len(PHASES)
    assert report["summary"]["data_workflow_step_count"] >= 3
    assert report["summary"]["rollback_criterion_count"] >= 3
    assert report["summary"]["training_touchpoint_count"] >= 3
    assert report["summary"]["integration_risk_count"] >= 1
    assert json.loads(json.dumps(report))["schema_version"] == SCHEMA_VERSION


def test_migration_phases_are_ordered_and_complete(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_migration_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    phases = report["migration_phases"]
    assert [phase["phase_type"] for phase in phases] == list(PHASES)
    assert [phase["sequence"] for phase in phases] == [1, 2, 3, 4, 5]
    assert all(
        {
            "id",
            "sequence",
            "phase_type",
            "name",
            "objective",
            "owner",
            "tasks",
            "acceptance_checks",
            "risks",
            "source_idea_ids",
        }
        <= set(phase)
        for phase in phases
    )
    assert all(phase["tasks"] for phase in phases)
    assert all(phase["acceptance_checks"] for phase in phases)
    assert all(phase["risks"] for phase in phases)
    assert all(phase["source_idea_ids"] for phase in phases)
    assert any("rollback" in task.lower() for phase in phases for task in phase["tasks"])


def test_steps_risks_training_and_evidence_are_traceable(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_migration_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert any(
        "manual release checklist" in step["migration_action"]
        for step in report["data_workflow_migration_steps"]
    )
    assert any("pilot users" in item["content"] for item in report["training_touchpoints"])
    assert any("Security review" in risk["risk"] for risk in report["integration_risks"])
    assert any("rollback" in item["response"].lower() or "Return affected users" in item["response"] for item in report["rollback_criteria"])
    assert any(item["id"] == "sig-migration-1" for item in report["evidence_references"])
    assert all(role["role"] for role in report["owner_roles"])
    assert all(
        item["source_idea_ids"]
        for collection in (
            report["data_workflow_migration_steps"],
            report["rollback_criteria"],
            report["training_touchpoints"],
            report["integration_risks"],
        )
        for item in collection
    )


def test_markdown_rendering_is_readable_and_has_no_python_reprs(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_migration_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_migration_plan(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_migration_plan(report, fmt="markdown")
    assert markdown.startswith("# Migration Plan: Migration Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Migration Phases" in markdown
    assert "### 1. Preparation and migration readiness" in markdown
    assert "### 5. Rollback and stabilization" in markdown
    assert "## Data and Workflow Migration Steps" in markdown
    assert "## Rollback Criteria" in markdown
    assert "## Training Touchpoints" in markdown
    assert "## Integration Risks" in markdown
    assert "Source idea references: bu-migration-lead, bu-migration-support" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown


def test_sparse_design_brief_returns_conservative_plan_with_warnings(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_migration_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert [phase["phase_type"] for phase in report["migration_phases"]] == list(PHASES)
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "current_workaround",
    ]
    assert report["summary"]["incumbent_workflow"] == "current manual or incumbent workflow"
    assert report["validation_warnings"]
    assert any(warning["field"] == "current_workaround" for warning in report["validation_warnings"])
    assert any("reversible pilot" in warning["warning"] for warning in report["validation_warnings"])
    assert all(phase["acceptance_checks"] for phase in report["migration_phases"])


def test_migration_plan_missing_brief_invalid_format_and_filename(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_migration_plan.db"), wal_mode=True)
    try:
        assert build_design_brief_migration_plan(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported migration plan format: yaml"):
        render_design_brief_migration_plan({"design_brief": {}}, fmt="yaml")

    design_brief = {"id": "dbf-123", "title": "Migration Plan: Alpha / Beta"}
    assert (
        migration_plan_filename(design_brief)
        == "dbf-123-Migration-Plan-Alpha-Beta-migration-plan.md"
    )
    assert (
        migration_plan_filename(design_brief, fmt="json")
        == "dbf-123-Migration-Plan-Alpha-Beta-migration-plan.json"
    )


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_migration_plan.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-migration-lead",
        title="Migration Lead",
        one_liner="Plan migrations from incumbent operational workflows.",
        category="application",
        problem="Teams need reversible rollout plans before replacing manual release reviews.",
        solution="Generate migration phases, rollback checks, and training gates from design briefs.",
        value_proposition="Make adoption safer for operational workflows.",
        specific_user="release manager",
        buyer="VP of Engineering",
        workflow_context="release approval workflow",
        current_workaround="manual release checklist",
        why_now="Generated specs need adoption planning before implementation handoff.",
        validation_plan="Run a two-team pilot and compare cycle time, support load, and rollback readiness.",
        first_10_customers="platform teams with weekly release governance",
        domain_risks=["Security review may block workflow migration."],
        evidence_signals=["sig-migration-1"],
        inspiring_insights=["ins-migration-1"],
        tech_approach="Deterministic Python artifact over persisted design brief fields.",
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-migration-support",
        title="Migration Support",
        one_liner="Track integration risk and enablement needs for adoption.",
        category="application",
        problem="Operational workflow replacements fail when integrations are not rehearsed.",
        solution="Attach integration risks, owners, and training touchpoints to the plan.",
        value_proposition="Give implementation agents an adoption checklist.",
        specific_user="platform engineer",
        buyer="engineering director",
        workflow_context="integration handoff",
        current_workaround="manual implementation checklist",
        domain_risks=["Legacy API sync can create duplicate approval records."],
        evidence_signals=["sig-migration-2"],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Migration Plan Brief",
            domain="developer-tools",
            theme="migration-plan",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=78.0,
            why_this_now="Generated ideas increasingly target workflows that require adoption planning.",
            merged_product_concept="A workflow migration plan artifact for design briefs.",
            synthesis_rationale="Extends specs with migration, rollback, and training detail.",
            mvp_scope=["Migration plan JSON artifact", "Markdown migration plan export"],
            first_milestones=["Pilot migration with two platform teams"],
            validation_plan="Run a two-team pilot and compare cycle time, support load, and rollback readiness.",
            risks=[
                "Security review may block workflow migration.",
                "Legacy API sync can create duplicate approval records.",
            ],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_migration_plan.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-migration-sparse",
        title="Sparse Migration Lead",
        one_liner="Create migration planning defaults with weak context.",
        category="application",
        problem="Adoption planning inputs are incomplete.",
        solution="Use conservative migration phases and warnings.",
        value_proposition="Keep planning moving without hiding missing inputs.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Migration Brief",
            domain="developer-tools",
            theme="migration-plan",
            lead=Candidate(unit=lead),
            readiness_score=32.0,
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
