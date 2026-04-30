"""Tests for design brief RACI matrix generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_raci_matrix import (
    SCHEMA_VERSION,
    build_design_brief_raci_matrix,
    raci_matrix_filename,
    render_design_brief_raci_matrix,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_raci_matrix_roles_phases_and_activities(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        matrix = build_design_brief_raci_matrix(store, brief_id)
        repeated = build_design_brief_raci_matrix(store, brief_id)
    finally:
        store.close()

    assert matrix == repeated
    assert matrix is not None
    assert matrix["schema_version"] == SCHEMA_VERSION
    assert matrix["kind"] == "max.design_brief.raci_matrix"
    assert matrix["design_brief"]["id"] == brief_id
    assert matrix["design_brief"]["buyer"] == "VP of Operations"
    assert matrix["design_brief"]["specific_user"] == "implementation manager"
    assert matrix["summary"] == {
        "phase_count": 4,
        "activity_count": 8,
        "role_count": 6,
        "gap_count": 0,
        "escalation_note_count": 4,
        "source_idea_count": 2,
    }
    assert [phase["id"] for phase in matrix["phases"]] == [
        "alignment",
        "implementation_handoff",
        "validation",
        "launch_readiness",
    ]
    assert [activity["id"] for activity in matrix["activities"]] == [
        f"DBRACI{index}" for index in range(1, 9)
    ]
    assert all(activity["responsible_role"] for activity in matrix["activities"])
    assert all(activity["accountable_role"] for activity in matrix["activities"])
    assert all(isinstance(activity["consulted_roles"], list) for activity in matrix["activities"])
    assert all(isinstance(activity["informed_roles"], list) for activity in matrix["activities"])
    assert all(activity["source_fields"] for activity in matrix["activities"])
    assert all(activity["ownership_status"] == "assigned" for activity in matrix["activities"])
    assert matrix["activities"][0]["accountable_role"] == "VP of Operations"
    assert matrix["activities"][4]["responsible_role"] == "implementation manager"
    assert matrix["activities"][5]["responsible_role"] == "Security/legal approver"
    assert any(
        assignment["role"] == "Support/playbook owner"
        and assignment["responsible_activity_ids"] == ["DBRACI4", "DBRACI8"]
        for assignment in matrix["role_assignments"]
    )
    assert json.loads(json.dumps(matrix))["design_brief"]["id"] == brief_id


def test_build_design_brief_raci_matrix_sparse_brief_surfaces_ownership_gaps(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        matrix = build_design_brief_raci_matrix(store, brief_id)
    finally:
        store.close()

    assert matrix is not None
    assert matrix["design_brief"]["buyer"] == "TBD buyer owner"
    assert matrix["design_brief"]["specific_user"] == "TBD primary user"
    assert [gap["field"] for gap in matrix["gaps"]] == [
        "buyer",
        "specific_user",
        "validation_plan",
        "risks",
        "support_needs",
    ]
    assert all(gap["resolution"].startswith("Name the ") for gap in matrix["gaps"])
    gap_rows = [activity for activity in matrix["activities"] if activity["ownership_status"] == "gap"]
    assert [activity["id"] for activity in gap_rows] == [
        "DBRACI1",
        "DBRACI2",
        "DBRACI4",
        "DBRACI5",
        "DBRACI6",
        "DBRACI7",
        "DBRACI8",
    ]
    assert matrix["activities"][0]["accountable_role"] == "TBD buyer owner"
    assert matrix["activities"][4]["responsible_role"] == "TBD validation owner"
    assert matrix["activities"][5]["responsible_role"] == "TBD risk approver"
    assert matrix["escalation_notes"][0].startswith("Resolve explicit ownership gaps")


def test_render_design_brief_raci_matrix_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        matrix = build_design_brief_raci_matrix(store, brief_id)
    finally:
        store.close()

    assert matrix is not None
    markdown = render_design_brief_raci_matrix(matrix)
    assert markdown.startswith("# RACI Matrix: RACI Matrix Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Alignment" in markdown
    assert "## Implementation Handoff" in markdown
    assert "## Validation" in markdown
    assert "## Launch Readiness" in markdown
    assert "| Activity | Responsible | Accountable | Consulted | Informed | Gaps |" in markdown
    assert (
        "| Confirm buyer outcome and approval path. | Product lead | VP of Operations | "
        "implementation manager, Security/legal approver | Engineering lead | none |"
    ) in markdown
    assert "## Escalation Notes" in markdown

    rendered_once = render_design_brief_raci_matrix(matrix, fmt="json")
    rendered_twice = render_design_brief_raci_matrix(matrix, fmt="json")
    assert rendered_once == rendered_twice
    assert json.loads(rendered_once) == matrix

    with pytest.raises(ValueError, match="Unsupported RACI matrix format: yaml"):
        render_design_brief_raci_matrix(matrix, fmt="yaml")


def test_build_design_brief_raci_matrix_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_raci_matrix.db"), wal_mode=True)
    try:
        matrix = build_design_brief_raci_matrix(store, "dbf-missing")
    finally:
        store.close()

    assert matrix is None


def test_raci_matrix_filename_uses_brief_id_and_title() -> None:
    assert (
        raci_matrix_filename(
            {"id": "dbf-test001", "title": "RACI Matrix API Brief"},
            fmt="markdown",
        )
        == "dbf-test001-RACI-Matrix-API-Brief-raci-matrix.md"
    )
    assert (
        raci_matrix_filename(
            {"id": "dbf-test001", "title": "RACI Matrix API Brief"},
            fmt="json",
        )
        == "dbf-test001-RACI-Matrix-API-Brief-raci-matrix.json"
    )


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_raci_matrix_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-raci-sparse-lead",
            title="Sparse RACI Lead",
            one_liner="Generate sparse RACI matrices.",
            category="application",
            problem="Handoffs need explicit ownership gaps.",
            solution="Build RACI matrix fallbacks.",
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
            composability_notes="",
            domain="developer-tools",
            status="approved",
        )
        supporting: list[Candidate] = []
        risks: list[str] = []
        validation_plan = ""
    else:
        lead = BuildableUnit(
            id="bu-raci-lead",
            title="RACI Matrix Lead",
            one_liner="Prepare RACI handoffs from design briefs.",
            category="application",
            problem="Implementation agents and project managers need ownership clarity.",
            solution="Export deterministic RACI matrices from persisted design briefs.",
            value_proposition="Reduce launch handoff ambiguity for organizational buyers.",
            specific_user="implementation manager",
            buyer="VP of Operations",
            workflow_context="enterprise workflow rollout with customer data",
            current_workaround="manual handoff docs",
            why_now="Design briefs increasingly support implementation handoffs.",
            validation_plan="Run RACI review with two pilot implementation managers.",
            first_10_customers="mid-market operations teams with formal launch playbooks",
            domain_risks=[
                "Security and privacy review may delay customer data access.",
                "Support ownership may be unclear after pilot launch.",
            ],
            evidence_rationale="Signals show ownership, support, and launch readiness gaps.",
            evidence_signals=["sig-raci-ownership", "sig-raci-launch"],
            inspiring_insights=["ins-raci"],
            tech_approach="FastAPI and persisted RACI generation with audit-friendly JSON.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            composability_notes="Create a reusable project-manager playbook export.",
            domain="developer-tools",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-raci-support",
            title="RACI Matrix Support",
            one_liner="Support launch handoff playbooks.",
            category="automation",
            problem="Support teams need playbooks before rollout.",
            solution="Attach playbook responsibilities to RACI rows.",
            value_proposition="Make support ownership explicit.",
            specific_user="support operations lead",
            buyer="VP of Operations",
            workflow_context="pilot support workflow",
            current_workaround="ad hoc support notes",
            validation_plan="Test support escalation during pilot.",
            first_10_customers="operations teams with shared support queues",
            domain_risks=["Launch support can miss escalation coverage."],
            evidence_rationale="Support gaps appear during pilot handoffs.",
            tech_approach="Generate support playbook rows.",
            composability_notes="Playbook template for support and rollout ownership.",
            domain="developer-tools",
            status="approved",
        )
        supporting = [Candidate(unit=support)]
        risks = ["Legal review is required before customer workflow data is used."]
        validation_plan = "Confirm RACI traceability with implementation and budget owners."

    store.insert_buildable_unit(lead)
    for candidate in supporting:
        store.insert_buildable_unit(candidate.unit)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="RACI Matrix Brief",
            domain="developer-tools",
            theme="handoff-ownership",
            lead=Candidate(unit=lead),
            supporting=supporting,
            readiness_score=88.0,
            why_this_now="Design briefs increasingly support handoff workflows.",
            merged_product_concept="A RACI matrix export for persisted design briefs.",
            synthesis_rationale="Connects buyer, user, implementation, support, risk, and launch ownership.",
            mvp_scope=["JSON RACI matrix", "Markdown RACI matrix"],
            first_milestones=["Return RACI matrix JSON", "Render grouped Markdown table"],
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id, *[candidate.unit.id for candidate in supporting]],
            design_status="approved",
        )
    )
    return store, brief_id
