"""Tests for design brief operating model analysis."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis import (
    build_design_brief_operating_model as exported_build,
    render_design_brief_operating_model as exported_render,
)
from max.analysis.design_brief_operating_model import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_operating_model,
    render_design_brief_operating_model,
    render_design_brief_operating_model_csv,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_operating_model_has_stable_shape(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        first = build_design_brief_operating_model(store, brief_id)
        second = build_design_brief_operating_model(store, brief_id)
    finally:
        store.close()

    assert first == second
    assert first is not None
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.operating_model"
    assert first["design_brief"]["id"] == brief_id
    assert first["design_brief"]["title"] == "Operating Model Brief"
    assert first["design_brief"]["source_idea_ids"] == ["bu-ops-lead", "bu-ops-support"]
    assert first["summary"] == {
        "title": "Operating Model Brief",
        "operating_owner": "Product lead",
        "buyer": "VP of Operations",
        "primary_user": "implementation manager",
        "workflow_context": "enterprise workflow rollout with customer data",
        "implementation_owner": "Engineering lead",
        "support_owner": "Support owner",
        "risk_owner": "Security/legal owner",
        "operating_posture": "ready_for_pilot_operations",
        "ritual_count": 3,
        "decision_right_count": 3,
        "escalation_path_count": 3,
        "handoff_checkpoint_count": 3,
        "operating_metric_count": 3,
        "fallbacks_used": [],
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "design_brief",
        "summary",
        "operating_rituals",
        "decision_rights",
        "escalation_paths",
        "handoff_checkpoints",
        "operating_metrics",
        "evidence_references",
    }
    assert [item["id"] for item in first["operating_rituals"]] == ["OMR1", "OMR2", "OMR3"]
    assert [item["id"] for item in first["decision_rights"]] == ["OMD1", "OMD2", "OMD3"]
    assert [item["id"] for item in first["escalation_paths"]] == ["OME1", "OME2", "OME3"]
    assert [item["id"] for item in first["handoff_checkpoints"]] == ["OMH1", "OMH2", "OMH3"]
    assert [item["id"] for item in first["operating_metrics"]] == ["OMM1", "OMM2", "OMM3"]
    assert first["operating_rituals"][0]["owner"] == "Product lead"
    assert first["operating_rituals"][0]["participants"] == [
        "VP of Operations",
        "implementation manager",
        "Engineering lead",
    ]
    assert first["decision_rights"][0]["approver"] == "VP of Operations"
    assert first["escalation_paths"][2]["trigger"] == (
        "Legal review is required before customer workflow data is used."
    )
    assert first["operating_metrics"][0]["target"] == (
        "80% of pilot attempts complete without owner intervention"
    )
    assert [item["reference"] for item in first["evidence_references"]] == [
        "design_brief.buyer",
        "design_brief.specific_user",
        "design_brief.workflow_context",
        "design_brief.validation_plan",
        "design_brief.mvp_scope",
        "design_brief.first_milestones",
        "design_brief.risks",
        "idea:bu-ops-lead",
        "idea:bu-ops-support",
    ]


def test_sparse_design_brief_uses_default_owners_and_rituals(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_operating_model(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["buyer"] == "launch sponsor"
    assert report["summary"]["primary_user"] == "primary workflow owner"
    assert report["summary"]["workflow_context"] == "primary workflow"
    assert report["summary"]["risk_owner"] == "Risk owner"
    assert report["summary"]["operating_posture"] == "needs_owner_confirmation"
    assert report["summary"]["fallbacks_used"] == [
        "buyer",
        "specific_user",
        "workflow_context",
        "validation_plan",
        "first_milestones",
        "mvp_scope",
        "tech_approach",
    ]
    assert report["operating_rituals"][0]["participants"] == [
        "launch sponsor",
        "primary workflow owner",
        "Engineering lead",
    ]
    assert report["decision_rights"][0]["inputs"] == [
        "Confirm pilot success criteria with the launch sponsor.",
        "Complete pilot handoff",
    ]
    assert report["escalation_paths"][2]["trigger"] == (
        "No explicit risk captured; escalate unknown blockers."
    )
    assert report["evidence_references"] == [{"type": "source_idea", "reference": "idea:bu-ops-sparse-lead"}]


def test_render_design_brief_operating_model_markdown_json_and_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_operating_model(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_operating_model(report)
    assert markdown.startswith("# Operating Model: Operating Model Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "Operating owner: Product lead" in markdown
    assert "## Operating Rituals" in markdown
    assert "## Decision Rights" in markdown
    assert "## Escalation Paths" in markdown
    assert "## Handoff Checkpoints" in markdown
    assert "## Operating Metrics" in markdown
    assert "## Evidence References" in markdown
    assert "OMR1 Operating review" in markdown
    assert "enterprise workflow rollout with customer data progress" in markdown

    rendered_once = render_design_brief_operating_model(report, fmt="json")
    rendered_twice = render_design_brief_operating_model(report, fmt="json")
    assert rendered_once == rendered_twice
    assert json.loads(rendered_once) == report

    with pytest.raises(ValueError, match="Unsupported operating model format: yaml"):
        render_design_brief_operating_model(report, fmt="yaml")


def test_render_design_brief_operating_model_csv_is_parseable_and_stable(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_operating_model(store, brief_id)
    finally:
        store.close()

    assert report is not None
    first = render_design_brief_operating_model(report, fmt="csv")
    second = render_design_brief_operating_model_csv(report)
    reader = csv.DictReader(io.StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert len(rows) == 15

    ritual_row = rows[0]
    assert ritual_row["design_brief_id"] == brief_id
    assert ritual_row["design_brief_title"] == "Operating Model Brief"
    assert ritual_row["section"] == "operating_rituals"
    assert ritual_row["item_id"] == "OMR1"
    assert ritual_row["name"] == "Operating review"
    assert ritual_row["owner"] == "Product lead"
    assert ritual_row["cadence"] == "weekly during pilot"
    assert "metric movement" in ritual_row["description"]
    assert json.loads(ritual_row["evidence_refs"]) == [
        "design_brief.workflow_context",
        "design_brief.validation_plan",
    ]
    assert json.loads(ritual_row["source_idea_ids"]) == ["bu-ops-lead", "bu-ops-support"]

    decision_row = next(row for row in rows if row["section"] == "decision_rights" and row["item_id"] == "OMD1")
    assert decision_row["decision"] == "Pilot entry"
    assert decision_row["approver"] == "VP of Operations"

    metric_row = next(row for row in rows if row["section"] == "operating_metrics" and row["item_id"] == "OMM3")
    assert metric_row["metric"] == "Escalation resolution"
    assert metric_row["target"] == (
        "High-severity pilot escalations have an owner and next action within 1 business day"
    )


def test_operating_model_missing_brief_returns_none_and_exports_work(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_operating_model.db"), wal_mode=True)
    try:
        assert build_design_brief_operating_model(store, "dbf-missing") is None

        _, brief_id = _insert_operating_model_brief(store)
        report = exported_build(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(exported_render(report, fmt="json"))["design_brief"]["id"] == brief_id


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_operating_model_{sparse}.db"),
        wal_mode=True,
    )
    brief_id = _insert_operating_model_brief(store, sparse=sparse)[1]
    return store, brief_id


def _insert_operating_model_brief(store: Store, *, sparse: bool = False) -> tuple[BuildableUnit, str]:
    if sparse:
        lead = BuildableUnit(
            id="bu-ops-sparse-lead",
            title="Sparse Operating Model Lead",
            one_liner="Generate sparse operating models.",
            category="application",
            problem="Approved briefs need default operating rituals.",
            solution="Build fallback operating model reports.",
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
        mvp_scope: list[str] = []
        first_milestones: list[str] = []
    else:
        lead = BuildableUnit(
            id="bu-ops-lead",
            title="Operating Model Lead",
            one_liner="Prepare operating models from design briefs.",
            category="application",
            problem="Implementation teams need repeatable operating ownership.",
            solution="Export deterministic operating models from persisted design briefs.",
            value_proposition="Reduce launch ambiguity for organizational buyers.",
            specific_user="implementation manager",
            buyer="VP of Operations",
            workflow_context="enterprise workflow rollout with customer data",
            current_workaround="manual operating docs",
            why_now="Design briefs increasingly support launch operations.",
            validation_plan="Run operating review with two pilot implementation managers.",
            first_10_customers="mid-market operations teams with formal launch playbooks",
            domain_risks=[
                "Security and privacy review may delay customer data access.",
                "Support ownership may be unclear after pilot launch.",
            ],
            evidence_rationale="Signals show owner, support, and launch readiness gaps.",
            evidence_signals=["sig-ops-ownership", "sig-ops-launch"],
            inspiring_insights=["ins-ops"],
            tech_approach="FastAPI and persisted operating model generation.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            composability_notes="Create a reusable project-manager operating cadence export.",
            domain="developer-tools",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-ops-support",
            title="Operating Model Support",
            one_liner="Support launch operating rituals.",
            category="automation",
            problem="Support teams need operating cadence before rollout.",
            solution="Attach support responsibilities to operating model rows.",
            value_proposition="Make support ownership explicit.",
            specific_user="support operations lead",
            buyer="VP of Operations",
            workflow_context="pilot support workflow",
            current_workaround="ad hoc support notes",
            validation_plan="Test support escalation during pilot.",
            first_10_customers="operations teams with shared support queues",
            domain_risks=["Launch support can miss escalation coverage."],
            evidence_rationale="Support gaps appear during pilot handoffs.",
            tech_approach="Generate support operating rows.",
            composability_notes="Playbook template for support and rollout ownership.",
            domain="developer-tools",
            status="approved",
        )
        supporting = [Candidate(unit=support)]
        risks = ["Legal review is required before customer workflow data is used."]
        validation_plan = "Confirm operating model traceability with implementation and budget owners."
        mvp_scope = ["JSON operating model", "Markdown operating model"]
        first_milestones = ["Return operating model JSON", "Render grouped Markdown plan"]

    store.insert_buildable_unit(lead)
    for candidate in supporting:
        store.insert_buildable_unit(candidate.unit)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Operating Model Brief",
            domain="developer-tools",
            theme="operating-ownership",
            lead=Candidate(unit=lead),
            supporting=supporting,
            readiness_score=88.0,
            why_this_now="Design briefs increasingly support operating workflows.",
            merged_product_concept="An operating model export for approved design briefs.",
            synthesis_rationale="Connects buyer, user, implementation, support, risk, and launch ownership.",
            mvp_scope=mvp_scope,
            first_milestones=first_milestones,
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id, *[candidate.unit.id for candidate in supporting]],
            design_status="approved",
        )
    )
    return lead, brief_id
