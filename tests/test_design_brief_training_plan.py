"""Tests for design brief training plan generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_training_plan import (
    CSV_COLUMNS,
    CSV_SECTIONS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_training_plan,
    render_design_brief_training_plan,
    training_plan_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_training_plan_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_training_plan(store, brief_id)
        repeated = build_design_brief_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["buyer"] == "engineering director"
    assert report["summary"]["target_user"] == "platform lead"
    assert report["summary"]["fallbacks_used"] == []
    assert [segment["id"] for segment in report["learner_segments"]] == [
        "customer_practitioners",
        "customer_sponsors",
        "internal_gtm_support",
        "internal_product_engineering",
    ]
    assert [objective["id"] for objective in report["learning_objectives"]] == [
        "LO1",
        "LO2",
        "LO3",
        "LO4",
    ]
    assert [item["id"] for item in report["session_outline"]] == ["SO1", "SO2", "SO3", "SO4"]
    assert [item["id"] for item in report["prerequisite_setup"]] == ["PS1", "PS2", "PS3"]
    assert [exercise["id"] for exercise in report["hands_on_exercises"]] == ["EX1", "EX2", "EX3"]
    assert [check["id"] for check in report["success_checks"]] == ["SC1", "SC2", "SC3", "SC4"]
    assert [material["id"] for material in report["follow_up_materials"]] == ["FM1", "FM2", "FM3"]
    assert any(item["id"] == "sig-training-1" for item in report["evidence_references"])
    assert report["gaps_to_resolve"] == []
    assert report["next_actions"] == []
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_sparse_design_brief_training_plan_adds_gaps_and_next_actions(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == ["buyer", "specific_user", "workflow_context"]
    fields = [gap["field"] for gap in report["gaps_to_resolve"]]
    assert fields == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
        "validation_plan",
        "readiness_score",
        "evidence_references",
    ]
    assert [action["gap_id"] for action in report["next_actions"]] == [
        gap["id"] for gap in report["gaps_to_resolve"]
    ]
    assert report["learner_segments"][0]["training_need"].startswith("Complete first usable")
    assert all(gap["next_action"] for gap in report["gaps_to_resolve"])


def test_render_design_brief_training_plan_markdown_and_json(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_training_plan(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_training_plan(report, fmt="markdown")
    assert markdown.startswith("# Training Plan: Training Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Training Summary" in markdown
    assert "## Learner Segments" in markdown
    assert "## Learning Objectives" in markdown
    assert "## Session Outline" in markdown
    assert "## Prerequisite Setup" in markdown
    assert "## Hands-On Exercises" in markdown
    assert "## Success Checks" in markdown
    assert "## Follow-Up Materials" in markdown
    assert "## Evidence References" in markdown
    assert "## Gaps To Resolve Before Training" in markdown
    assert "## Next Actions" in markdown


def test_render_design_brief_training_plan_csv_headers_and_sections(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered = render_design_brief_training_plan(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(rendered)))

    assert rendered.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows
    assert set(rows[0]) == set(CSV_COLUMNS)
    assert {row["section"] for row in rows} == set(CSV_SECTIONS)
    assert {row["design_brief_id"] for row in rows} == {brief_id}
    assert {row["design_brief_title"] for row in rows} == {"Sparse Training Brief"}


def test_render_design_brief_training_plan_csv_is_deterministic_and_serializes_nested_values(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    first = render_design_brief_training_plan(report, fmt="csv")
    second = render_design_brief_training_plan(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(first)))

    assert first == second
    lo1 = next(
        row
        for row in rows
        if row["section"] == "learning_objectives" and row["item_id"] == "LO1"
    )
    assert json.loads(lo1["details"]) == {
        "source_fields": ["specific_user", "workflow_context"],
        "source_idea_ids": ["bu-training-lead", "bu-training-support"],
    }
    assert lo1["details"] == (
        '{"source_fields":["specific_user","workflow_context"],'
        '"source_idea_ids":["bu-training-lead","bu-training-support"]}'
    )
    ex3 = next(
        row
        for row in rows
        if row["section"] == "hands_on_exercises" and row["item_id"] == "EX3"
    )
    assert json.loads(ex3["details"])["learning_objective_ids"] == ["LO1", "LO2", "LO3", "LO4"]


def test_render_design_brief_training_plan_csv_does_not_change_json_or_markdown(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    before_json = render_design_brief_training_plan(report, fmt="json")
    before_markdown = render_design_brief_training_plan(report, fmt="markdown")

    render_design_brief_training_plan(report, fmt="csv")

    assert render_design_brief_training_plan(report, fmt="json") == before_json
    assert json.loads(before_json) == report
    assert render_design_brief_training_plan(report, fmt="markdown") == before_markdown
    assert before_markdown.startswith("# Training Plan: Training Plan Brief")
    assert f"Design brief: `{brief_id}`" in before_markdown


def test_training_plan_filename_generation() -> None:
    design_brief = {"id": "dbf-123", "title": "Training Plan: Alpha / Beta"}

    assert (
        training_plan_filename(design_brief)
        == "dbf-123-Training-Plan-Alpha-Beta-training-plan.md"
    )
    assert (
        training_plan_filename(design_brief, fmt="json")
        == "dbf-123-Training-Plan-Alpha-Beta-training-plan.json"
    )
    assert (
        training_plan_filename(design_brief, fmt="csv")
        == "dbf-123-Training-Plan-Alpha-Beta-training-plan.csv"
    )


def test_training_plan_missing_brief_and_invalid_format(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_training_plan.db"), wal_mode=True)
    try:
        assert build_design_brief_training_plan(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported training plan format: yaml"):
        render_design_brief_training_plan({"design_brief": {}}, fmt="yaml")


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_training_plan.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-training-lead",
        title="Training Lead",
        one_liner="Create repeatable training for a design brief workflow.",
        category="application",
        problem="Teams lack a structured training path after launch planning.",
        solution="Generate customer and internal training plans from persisted briefs.",
        value_proposition="Make adoption support repeatable after product rollout.",
        specific_user="platform lead",
        buyer="engineering director",
        workflow_context="internal developer platform adoption",
        current_workaround="manual enablement calls",
        why_now="Design briefs already capture the workflow and validation inputs.",
        validation_plan="Run a live training with two pilot teams and compare exercise completion.",
        first_10_customers="developer platform teams",
        domain_risks=["Learners may not have test workspace access."],
        evidence_signals=["sig-training-1"],
        inspiring_insights=["ins-training-1"],
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-training-support",
        title="Training Support",
        one_liner="Prepare internal coaching materials for customer training.",
        category="application",
        problem="Support and success need consistent training follow-up.",
        solution="Attach exercises, checks, and follow-up materials to the brief.",
        value_proposition="Give support teams repeatable coaching language.",
        specific_user="customer success manager",
        buyer="support director",
        workflow_context="customer training handoff",
        domain_risks=["Support owners may be unclear."],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Training Plan Brief",
            domain="developer-tools",
            theme="training-plan",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=86.0,
            why_this_now="The team needs training support after rollout planning.",
            merged_product_concept="A deterministic training plan for persisted design briefs.",
            synthesis_rationale="Extends design briefs into customer and internal adoption support.",
            mvp_scope=["Guided platform setup", "Role-specific exercise review"],
            first_milestones=["Pilot cohort completes the guided setup"],
            validation_plan="Run a live training with two pilot teams and compare exercise completion.",
            risks=["Learners may not have test workspace access."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_training_plan.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-training-sparse",
        title="Sparse Training Lead",
        one_liner="Create training with weak learner context.",
        category="application",
        problem="Training input is incomplete.",
        solution="Use deterministic fallback curriculum.",
        value_proposition="Keep training planning moving while gaps are visible.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Training Brief",
            domain="developer-tools",
            theme="training-plan",
            lead=Candidate(unit=lead),
            readiness_score=41.0,
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
