"""Tests for design brief onboarding checklist generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_onboarding_checklist import (
    SCHEMA_VERSION,
    build_design_brief_onboarding_checklist,
    onboarding_checklist_filename,
    render_design_brief_onboarding_checklist,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_onboarding_checklist_sections_and_evidence(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_onboarding_checklist(store, brief_id)
        repeated = build_design_brief_onboarding_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist == repeated
    assert checklist is not None
    assert checklist["schema_version"] == SCHEMA_VERSION
    assert checklist["kind"] == "max.design_brief.onboarding_checklist"
    assert checklist["design_brief"]["id"] == brief_id
    assert checklist["design_brief"]["buyer"] == "VP of Customer Success"
    assert checklist["summary"]["onboarding_gate"] == "ready_for_customer_onboarding"
    assert checklist["summary"]["setup_task_count"] == 3
    assert checklist["summary"]["data_access_requirement_count"] == 2
    assert checklist["summary"]["kickoff_agenda_count"] == 3
    assert checklist["summary"]["activation_milestone_count"] == 2
    assert checklist["summary"]["owner_role_count"] == 4
    assert checklist["summary"]["evidence_reference_count"] == 3
    assert [item["id"] for item in checklist["setup_tasks"]] == ["DBOC1", "DBOC2", "DBOC3"]
    assert [item["id"] for item in checklist["data_access_requirements"]] == [
        "DBOC4",
        "DBOC5",
    ]
    assert [item["id"] for item in checklist["checklist_items"]] == [
        "DBOC1",
        "DBOC2",
        "DBOC3",
        "DBOC4",
        "DBOC5",
        "KO1",
        "KO2",
        "KO3",
        "AM1",
        "AM2",
    ]
    assert all(item["owner_role"] for item in checklist["checklist_items"])
    assert all(ref["source_idea_ids"] for ref in checklist["evidence_references"])
    assert [ref["id"] for ref in checklist["evidence_references"]] == [
        "sig-onboarding-access",
        "sig-onboarding-activation",
        "pilot-users-need-guided-activation",
    ]
    assert json.loads(json.dumps(checklist))["design_brief"]["id"] == brief_id


def test_build_design_brief_onboarding_checklist_sparse_brief_uses_fallbacks(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        checklist = build_design_brief_onboarding_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    assert checklist["summary"]["onboarding_gate"] == "needs_onboarding_inputs"
    assert checklist["summary"]["fallbacks_used"] == [
        "buyer",
        "specific_user",
        "workflow_context",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
    ]
    assert checklist["onboarding_context"]["buyer"] == "pilot sponsor"
    assert checklist["onboarding_context"]["specific_user"] == "Sparse Onboarding Brief user"
    assert checklist["onboarding_context"]["workflow_context"] == (
        "Sparse Onboarding Brief pilot workflow"
    )
    assert [milestone["id"] for milestone in checklist["activation_milestones"]] == [
        "AM1",
        "AM2",
        "AM3",
    ]
    assert checklist["evidence_references"] == [
        {
            "id": "design-brief-lineage",
            "type": "lineage",
            "label": "Persisted design brief and source idea lineage.",
            "source_idea_ids": ["bu-onboarding-sparse-lead"],
        }
    ]


def test_render_design_brief_onboarding_checklist_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_onboarding_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    markdown = render_design_brief_onboarding_checklist(checklist)
    assert markdown.startswith("# Onboarding Checklist: Onboarding Checklist Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Setup Tasks" in markdown
    assert "## Data / Access Requirements" in markdown
    assert "## Kickoff Agenda" in markdown
    assert "## Activation Milestones" in markdown
    assert "## Owner Roles" in markdown
    assert "## Evidence References" in markdown
    assert "### DBOC1: Confirm pilot sponsor and onboarding owner" in markdown
    assert "- Owner role: Customer success owner" in markdown
    assert "- Completion evidence: Named sponsor, day-to-day owner" in markdown
    assert "**sig-onboarding-access** (signal)" in markdown

    parsed = json.loads(render_design_brief_onboarding_checklist(checklist, fmt="json"))
    assert parsed == checklist

    with pytest.raises(ValueError, match="Unsupported onboarding checklist format: yaml"):
        render_design_brief_onboarding_checklist(checklist, fmt="yaml")


def test_build_design_brief_onboarding_checklist_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_onboarding_checklist.db"), wal_mode=True)
    try:
        checklist = build_design_brief_onboarding_checklist(store, "dbf-missing")
    finally:
        store.close()

    assert checklist is None


def test_onboarding_checklist_filename_uses_brief_id_and_title() -> None:
    assert (
        onboarding_checklist_filename(
            {"id": "dbf-test001", "title": "Onboarding Checklist API Brief"},
            fmt="markdown",
        )
        == "dbf-test001-Onboarding-Checklist-API-Brief-onboarding-checklist.md"
    )
    assert (
        onboarding_checklist_filename(
            {"id": "dbf-test001", "title": "Onboarding Checklist API Brief"},
            fmt="json",
        )
        == "dbf-test001-Onboarding-Checklist-API-Brief-onboarding-checklist.json"
    )


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_onboarding_checklist_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-onboarding-sparse-lead",
            title="Sparse Onboarding Lead",
            one_liner="Generate sparse onboarding checklists.",
            category="application",
            problem="Onboarding handoffs need explicit fallbacks.",
            solution="Build onboarding readiness fallbacks.",
            value_proposition="",
            target_users="",
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
            domain="developer-tools",
            status="approved",
        )
        milestones: list[str] = []
        risks: list[str] = []
        validation_plan = ""
    else:
        lead = BuildableUnit(
            id="bu-onboarding-lead",
            title="Onboarding Checklist Lead",
            one_liner="Prepare customer onboarding after pilot approval.",
            category="application",
            problem="Pilot approvals do not include customer onboarding tasks.",
            solution="Export deterministic onboarding checklists from persisted design briefs.",
            value_proposition="Reduce time from pilot approval to first customer activation.",
            specific_user="customer success manager",
            buyer="VP of Customer Success",
            workflow_context="pilot customer activation workflow",
            current_workaround="manual kickoff notes and ad hoc access requests",
            why_now="Pilot execution needs repeatable customer handoff artifacts.",
            validation_plan="Confirm three pilot users complete their first activation workflow.",
            first_10_customers="B2B SaaS teams onboarding pilot customers",
            domain_risks=[
                "Customer data access may require security approval before setup.",
            ],
            evidence_rationale="Signals show access gaps and activation delays during handoff.",
            evidence_signals=["sig-onboarding-access", "sig-onboarding-activation"],
            inspiring_insights=["pilot users need guided activation"],
            tech_approach="FastAPI export backed by persisted design brief lineage.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            domain="developer-tools",
            status="approved",
        )
        milestones = ["Enable first pilot workspace", "Complete first activation workflow"]
        risks = ["Customer data access may require security approval before setup."]
        validation_plan = "Confirm pilot sponsor sees first activation evidence."

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Onboarding Brief" if sparse else "Onboarding Checklist Brief",
            domain="developer-tools",
            theme="onboarding-readiness",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=55.0 if sparse else 88.0,
            why_this_now="Pilot teams need onboarding readiness before customer exposure.",
            merged_product_concept="An onboarding checklist export for persisted design briefs.",
            synthesis_rationale="Connects setup, access, kickoff, activation, owners, and evidence.",
            mvp_scope=[] if sparse else ["Onboarding checklist JSON", "Onboarding checklist Markdown"],
            first_milestones=milestones,
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id],
            design_status="candidate" if sparse else "approved",
        )
    )
    return store, brief_id
