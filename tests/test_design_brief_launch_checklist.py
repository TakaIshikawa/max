"""Tests for design brief launch checklist generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_launch_checklist import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_launch_checklist,
    launch_checklist_filename,
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


def test_render_design_brief_launch_checklist_csv_rows_are_stable(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_launch_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    csv_text = render_design_brief_launch_checklist(checklist, fmt="csv")
    repeated = render_design_brief_launch_checklist(checklist, fmt="csv")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == len(checklist["checklist_items"])
    assert [row["item_id"] for row in rows] == [item["id"] for item in checklist["checklist_items"]]
    assert rows[0] == {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.launch_checklist",
        "design_brief_id": brief_id,
        "design_brief_title": "Launch Checklist Brief",
        "section_id": "readiness",
        "section_title": "Readiness",
        "section_owner_role": "Product lead",
        "item_id": "DBLC1",
        "task": "Confirm launch scope from the persisted MVP scope.",
        "status": "pending",
        "owner": "product_owner",
        "required": "true",
        "rationale": "JSON launch checklist; Markdown launch checklist",
        "exit_criteria": "MVP scope and explicit non-goals are approved for execution.",
        "source_idea_ids": "bu-launch-brief-lead;bu-launch-brief-support",
        "source_fields": "mvp_scope;merged_product_concept",
    }


def test_render_design_brief_launch_checklist_csv_escapes_special_characters(tmp_path) -> None:
    store, _brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_launch_checklist(store, _brief_id)
    finally:
        store.close()

    assert checklist is not None
    checklist["checklist_items"][0]["task"] = 'Confirm "launch", scope\nwith owner'
    checklist["checklist_items"][0]["rationale"] = 'Line one\nLine "two", with comma'

    csv_text = render_design_brief_launch_checklist(checklist, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert rows[0]["task"] == 'Confirm "launch", scope\nwith owner'
    assert rows[0]["rationale"] == 'Line one\nLine "two", with comma'


def test_render_design_brief_launch_checklist_csv_empty_items_header_only(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_launch_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    checklist = {**checklist, "checklist_items": []}

    assert render_design_brief_launch_checklist(checklist, fmt="csv") == ",".join(CSV_COLUMNS) + "\n"


def test_render_design_brief_launch_checklist_invalid_format_raises(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_launch_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    with pytest.raises(ValueError):
        render_design_brief_launch_checklist(checklist, fmt="yaml")


def test_launch_checklist_filename_supports_csv_extension() -> None:
    design_brief = {"id": "dbf launch/csv"}

    assert launch_checklist_filename(design_brief, fmt="markdown") == "dbf-launch-csv-launch-checklist.md"
    assert launch_checklist_filename(design_brief, fmt="json") == "dbf-launch-csv-launch-checklist.json"
    assert launch_checklist_filename(design_brief, fmt="csv") == "dbf-launch-csv-launch-checklist.csv"


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
