"""Tests for design brief pilot rollout plan generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_pilot_rollout import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_pilot_rollout,
    render_design_brief_pilot_rollout,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def reader_fieldnames(csv_text: str) -> list[str]:
    return list(csv.DictReader(io.StringIO(csv_text)).fieldnames or [])


def test_build_design_brief_pilot_rollout_translates_persisted_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_pilot_rollout(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.pilot_rollout"
    assert report["design_brief"]["id"] == brief_id
    assert report["pilot_cohort"]["target_users"] == "product operator"
    assert report["pilot_cohort"]["buyer"] == "product lead"
    assert report["entry_criteria"][0] == (
        "MVP scope is limited to: Pilot rollout JSON, Pilot rollout Markdown."
    )
    assert [phase["id"] for phase in report["rollout_phases"]] == [
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
    ]
    assert all(
        {"owner", "goal", "duration", "exit_criteria"} <= set(phase)
        for phase in report["rollout_phases"]
    )
    assert [item["metric"] for item in report["success_thresholds"]] == [
        "Workflow completion",
        "Repeat value",
        "Evidence coverage",
        "Concept fit",
    ]
    assert any("Privacy review" in item for item in report["stop_conditions"])
    assert [task["owner"] for task in report["operator_tasks"]] == [
        "Product lead",
        "Engineering lead",
        "Research lead",
        "Support owner",
        "Risk owner",
    ]
    assert [touchpoint["when"] for touchpoint in report["customer_touchpoints"]] == [
        "Kickoff",
        "First session",
        "Midpoint",
        "Closeout",
    ]
    assert report["evidence_gaps"] == []
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_build_design_brief_pilot_rollout_records_evidence_gaps(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_pilot_rollout(store, brief_id)
    finally:
        store.close()

    assert report is not None
    fields = [gap["field"] for gap in report["evidence_gaps"]]
    assert "specific_user" in fields
    assert "buyer" in fields
    assert "workflow_context" in fields
    assert "validation_plan" in fields
    assert "mvp_scope" in fields
    assert "risks" in fields
    assert "source_evidence" in fields
    assert any("source_evidence" in item for item in report["stop_conditions"])


def test_render_design_brief_pilot_rollout_markdown_is_deterministic(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_pilot_rollout(store, brief_id)
    finally:
        store.close()

    assert report is not None
    first = render_design_brief_pilot_rollout(report)
    second = render_design_brief_pilot_rollout(report, fmt="markdown")

    assert first == second
    assert first.startswith("# Pilot Rollout Plan: Pilot Rollout Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in first
    assert f"Design brief: `{brief_id}`" in first
    assert "## Pilot Cohort" in first
    assert "## Entry Criteria" in first
    assert "## Rollout Phases" in first
    assert "### phase-1: Pilot Prep" in first
    assert "- Owner: Product lead" in first
    assert (
        "- Goal: Confirm cohort, scope, success metrics, and risk owners before any customer exposure."
        in first
    )
    assert "- Duration: 3-5 business days" in first
    assert (
        "- Exit criteria: Pilot cohort, entry criteria, stop conditions, and evidence capture plan are approved."
        in first
    )
    assert "## Success Thresholds" in first
    assert "## Stop Conditions" in first
    assert "## Operator Tasks" in first
    assert "## Customer Touchpoints" in first
    assert "## Evidence Gaps" in first
    assert "- None" in first

    rendered_json = render_design_brief_pilot_rollout(report, fmt="json")
    assert json.loads(rendered_json) == report
    with pytest.raises(ValueError, match="Unsupported pilot rollout format: yaml"):
        render_design_brief_pilot_rollout(report, fmt="yaml")


def test_render_design_brief_pilot_rollout_csv_headers_sections_and_order(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_pilot_rollout(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_pilot_rollout(report, fmt="csv")
    repeated = render_design_brief_pilot_rollout(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert reader_fieldnames(csv_text) == list(CSV_COLUMNS)
    assert len(rows) == 1 + 5 + 4 + 4 + 4 + 5 + 4
    assert [row["section"] for row in rows] == [
        "pilot_cohort",
        *(["entry_criteria"] * 5),
        *(["rollout_phases"] * 4),
        *(["success_thresholds"] * 4),
        *(["stop_conditions"] * 4),
        *(["operator_tasks"] * 5),
        *(["customer_touchpoints"] * 4),
    ]
    assert rows[0]["item_id"] == "pilot-cohort"
    assert rows[0]["name"] == "product operator"
    assert rows[0]["owner"] == "product lead"
    assert rows[0]["timing"] == "pilot recruitment"
    assert rows[0]["success_or_exit_criteria"] == "3-5 qualified teams"
    assert rows[0]["evidence_or_output"] == "internal product operators"
    assert [row["item_id"] for row in rows[1:6]] == [
        "entry-1",
        "entry-2",
        "entry-3",
        "entry-4",
        "entry-5",
    ]
    assert [row["item_id"] for row in rows[6:10]] == [
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
    ]
    assert rows[6]["name"] == "Pilot Prep"
    assert rows[6]["owner"] == "Product lead"
    assert rows[6]["timing"] == "3-5 business days"
    assert rows[6]["goal_or_task"] == (
        "Confirm cohort, scope, success metrics, and risk owners before any customer exposure."
    )
    assert rows[6]["success_or_exit_criteria"] == (
        "Pilot cohort, entry criteria, stop conditions, and evidence capture plan are approved."
    )
    assert rows[10]["name"] == "Workflow completion"
    assert rows[10]["goal_or_task"] == "Workflow completion"
    assert rows[10]["evidence_or_output"] == (
        "Observed sessions, event logs, or customer-confirmed completion notes."
    )
    assert rows[14]["item_id"] == "stop-1"
    assert rows[18]["item_id"] == "operator-task-1"
    assert rows[18]["timing"] == "weekly"
    assert rows[18]["evidence_or_output"] == "Decision log with owner and date."
    assert rows[23]["item_id"] == "touchpoint-1"
    assert rows[23]["timing"] == "Kickoff"


def test_render_design_brief_pilot_rollout_csv_includes_gaps(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_pilot_rollout(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_pilot_rollout(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    gap_rows = [row for row in rows if row["section"] == "evidence_gaps"]

    assert len(gap_rows) == len(report["evidence_gaps"])
    assert [row["item_id"] for row in gap_rows] == [
        "evidence-gap-specific_user",
        "evidence-gap-buyer",
        "evidence-gap-workflow_context",
        "evidence-gap-validation_plan",
        "evidence-gap-mvp_scope",
        "evidence-gap-risks",
        "evidence-gap-source_evidence",
    ]
    assert gap_rows[0]["success_or_exit_criteria"] == "Specific pilot user is not defined."
    assert gap_rows[0]["evidence_or_output"] == "Specific pilot user is not defined."
    assert gap_rows[0]["goal_or_task"] == (
        "Name the user role that will perform the pilot workflow."
    )


def test_render_design_brief_pilot_rollout_csv_escapes_commas_quotes_and_newlines(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_pilot_rollout(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["pilot_cohort"]["target_users"] = 'product, "ops"\nlead'
    report["operator_tasks"][0]["task"] = 'Track "launch", blockers\nand decisions.'

    csv_text = render_design_brief_pilot_rollout(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert '"product, ""ops""\nlead"' in csv_text
    assert '"Track ""launch"", blockers\nand decisions."' in csv_text
    assert rows[0]["name"] == 'product, "ops"\nlead'
    assert rows[18]["goal_or_task"] == 'Track "launch", blockers\nand decisions.'


def test_build_design_brief_pilot_rollout_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_pilot_rollout.db"), wal_mode=True)
    try:
        report = build_design_brief_pilot_rollout(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"pilot_rollout_{sparse}.db"), wal_mode=True)
    if sparse:
        lead = BuildableUnit(
            id="bu-pilot-sparse-lead",
            title="Sparse Pilot Lead",
            one_liner="Generate sparse pilot rollout plans.",
            category="application",
            problem="Pilot handoffs need explicit gaps.",
            solution="Build a rollout report with gap tracking.",
            value_proposition="Make missing pilot evidence visible.",
            specific_user="",
            buyer="",
            workflow_context="",
            validation_plan="",
            domain_risks=[],
            evidence_signals=[],
            inspiring_insights=[],
            domain="developer-tools",
            status="approved",
        )
        risks: list[str] = []
        mvp_scope: list[str] = []
    else:
        lead = BuildableUnit(
            id="bu-pilot-lead",
            title="Pilot Rollout Lead",
            one_liner="Prepare staged pilots from persisted design briefs.",
            category="application",
            problem="Generated project specs do not include a small pilot plan.",
            solution="Export a deterministic pilot rollout artifact.",
            value_proposition="Make design brief handoffs safer before expansion.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="design-to-build handoff",
            current_workaround="manual pilot notes",
            why_now="Design briefs already persist risks and validation plans.",
            validation_plan="Run three pilot handoffs and compare evidence captured.",
            first_10_customers="internal product operators",
            domain_risks=["Privacy review is required before customer workflow data is used."],
            evidence_signals=["sig-pilot"],
            inspiring_insights=["ins-pilot"],
            tech_approach="FastAPI route using deterministic analysis code.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        risks = ["Privacy review is required before customer workflow data is used."]
        mvp_scope = ["Pilot rollout JSON", "Pilot rollout Markdown"]

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Pilot Rollout Brief",
            domain="developer-tools",
            theme="pilot-rollout",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=84.0,
            why_this_now="Generated project specs need a staged pilot plan.",
            merged_product_concept="A pilot rollout export for persisted design briefs.",
            synthesis_rationale="Connects risks, validation, and staged rollout decisions.",
            mvp_scope=mvp_scope,
            first_milestones=["Return pilot rollout JSON", "Return pilot rollout Markdown"],
            validation_plan=""
            if sparse
            else "Confirm JSON and Markdown are actionable for handoff.",
            risks=risks,
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
