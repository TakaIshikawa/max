from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_scope_matrix import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_scope_matrix,
    render_design_brief_scope_matrix,
    scope_matrix_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _signal(signal_id: str, source_type: SignalSourceType, role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=f"{role}-fixture",
        title=f"{role.title()} scope evidence",
        content=f"Evidence for {role} scope decisions.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.84,
        metadata={"signal_role": role},
    )


def _unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Launch Workflow Copilot",
        one_liner="Scope matrix source idea",
        category="application",
        problem="Developer tools founders cannot coordinate launch workflow decisions.",
        solution="Create a launch workflow cockpit with recommendations and status.",
        value_proposition="Reduce launch planning drift for developer tools teams.",
        specific_user="developer tools founder",
        buyer="growth lead",
        workflow_context="design partner recruiting",
        why_now="Launch-planning artifacts are ready for implementation handoff.",
        validation_plan="Review the scoped workflow with two launch owners.",
        first_10_customers="seed-stage developer tools companies",
        evidence_signals=["sig-scope-forum", "sig-scope-survey", "sig-scope-funding"],
        domain_risks=["Scope may expand into full lifecycle campaign automation."],
        evidence_rationale="Signals show source ideas need bounded launch workflows.",
        domain="developer-tools",
        status="approved",
    )


def _seed_scope_brief(store: Store) -> str:
    for signal in (
        _signal("sig-scope-forum", SignalSourceType.FORUM, "problem"),
        _signal("sig-scope-survey", SignalSourceType.SURVEY, "market"),
        _signal("sig-scope-funding", SignalSourceType.FUNDING, "budget"),
    ):
        store.insert_signal(signal)

    lead = _unit("bu-scope-lead")
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Launch Workflow Copilot Brief",
            domain="developer-tools",
            theme="scope-matrix",
            lead=Candidate(unit=lead),
            readiness_score=88.0,
            why_this_now="Launch-planning artifacts are ready for implementation handoff.",
            merged_product_concept="A deterministic scope matrix for autonomous implementation agents.",
            synthesis_rationale="Source ideas show direct launch workflow pain.",
            mvp_scope=["JSON scope matrix", "Markdown scope matrix"],
            first_milestones=["Return structured MoSCoW recommendations"],
            validation_plan="Confirm the scoped artifact blocks ambiguous implementation work.",
            risks=["Scope may expand into full lifecycle campaign automation."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )


def _seed_sparse_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-scope-sparse",
        title="Sparse Scope Idea",
        one_liner="Sparse source idea",
        category="application",
        problem="Missing scope fields.",
        solution="Fill them later.",
        value_proposition="Make missing scope inputs visible.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Sparse Scope Brief",
            domain="developer-tools",
            theme="scope-matrix",
            lead=Candidate(unit=lead),
            readiness_score=34.0,
            merged_product_concept="A sparse scope matrix.",
            source_idea_ids=[lead.id],
        )
    )


def test_build_design_brief_scope_matrix_is_deterministic_and_bucketed(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_scope_brief(store)
        matrix = build_design_brief_scope_matrix(store, brief_id)
        repeated = build_design_brief_scope_matrix(store, brief_id)
    finally:
        store.close()

    assert matrix == repeated
    assert matrix is not None
    assert matrix["schema_version"] == SCHEMA_VERSION
    assert matrix["kind"] == KIND
    assert matrix["source"]["id"] == brief_id
    assert matrix["design_brief"]["id"] == brief_id
    assert matrix["design_brief"]["source_idea_ids"] == ["bu-scope-lead"]
    assert list(matrix["buckets"]) == ["must_have", "should_have", "could_have", "wont_have_now"]
    assert [item["id"] for item in matrix["items"]] == ["SM-M1", "SM-S1", "SM-C1", "SM-W1"]
    assert [item["bucket"] for item in matrix["items"]] == [
        "must_have",
        "should_have",
        "could_have",
        "wont_have_now",
    ]
    assert [item["confidence"] for item in matrix["items"]] == ["high", "high", "medium", "high"]
    assert matrix["summary"]["confidence"] == "high"
    must = matrix["buckets"]["must_have"][0]
    assert must["decision"] == "Deliver the narrow design partner recruiting workflow for developer tools founder."
    assert must["dependencies"] == ["specific_user", "workflow_context", "mvp_scope"]
    assert must["evidence_refs"] == ["sig-scope-forum", "sig-scope-funding", "sig-scope-survey"]
    assert matrix["buckets"]["wont_have_now"][0]["rationale"].endswith("before expanding.")
    assert matrix["missing_inputs"] == []


def test_render_design_brief_scope_matrix_json_markdown_and_invalid_format(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_scope_brief(store)
        matrix = build_design_brief_scope_matrix(store, brief_id)
    finally:
        store.close()

    assert matrix is not None
    parsed = json.loads(render_design_brief_scope_matrix(matrix, "json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_scope_matrix(matrix, "markdown")
    assert markdown.startswith("# Scope Decision Matrix: Launch Workflow Copilot Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Must Have" in markdown
    assert "## Should Have" in markdown
    assert "## Could Have" in markdown
    assert "## Won't Have Now" in markdown
    assert "SM-M1: Deliver the narrow design partner recruiting workflow" in markdown
    assert "sig-scope-funding" in markdown
    assert "## Missing Inputs" in markdown

    with pytest.raises(ValueError):
        render_design_brief_scope_matrix(matrix, "yaml")


def test_render_design_brief_scope_matrix_csv_is_structured_and_ordered(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_scope_brief(store)
        matrix = build_design_brief_scope_matrix(store, brief_id)
    finally:
        store.close()

    assert matrix is not None
    rendered = render_design_brief_scope_matrix(matrix, "csv")
    reader = csv.DictReader(io.StringIO(rendered))
    rows = list(reader)

    assert reader.fieldnames == [
        "design_brief_id",
        "bucket",
        "item_id",
        "decision",
        "confidence",
        "rationale",
        "dependencies",
        "evidence_refs",
        "source_idea_ids",
    ]
    assert len(rows) == len(matrix["items"])
    assert [row["item_id"] for row in rows] == [item["id"] for item in matrix["items"]]
    assert [row["bucket"] for row in rows] == [
        "must_have",
        "should_have",
        "could_have",
        "wont_have_now",
    ]
    assert {row["item_id"] for row in rows} == {item["id"] for item in matrix["items"]}
    assert all(row["design_brief_id"] == brief_id for row in rows)
    assert rows[0]["dependencies"] == "specific_user;workflow_context;mvp_scope"
    assert rows[0]["evidence_refs"] == "sig-scope-forum;sig-scope-funding;sig-scope-survey"
    assert rows[0]["source_idea_ids"] == "bu-scope-lead"


def test_scope_matrix_filename_supports_csv_extension() -> None:
    design_brief = {"id": "dbf scope/csv"}

    assert scope_matrix_filename(design_brief, "markdown") == "dbf-scope-csv-scope-matrix.md"
    assert scope_matrix_filename(design_brief, "json") == "dbf-scope-csv-scope-matrix.json"
    assert scope_matrix_filename(design_brief, "csv") == "dbf-scope-csv-scope-matrix.csv"


def test_build_design_brief_scope_matrix_reports_sparse_inputs_without_misleading_scope(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_sparse_brief(store)
        matrix = build_design_brief_scope_matrix(store, brief_id)
    finally:
        store.close()

    assert matrix is not None
    missing_fields = {item["field"] for item in matrix["missing_inputs"]}
    assert {"buyer", "specific_user", "workflow_context", "mvp_scope", "validation_plan", "risks"} <= missing_fields
    assert matrix["summary"]["confidence"] == "low"
    assert {item["confidence"] for item in matrix["items"]} == {"low"}
    assert matrix["buckets"]["must_have"][0]["decision"] == (
        "Complete the missing scope inputs before committing implementation work."
    )
    assert matrix["buckets"]["wont_have_now"][0]["decision"] == (
        "Do not generate implementation scope from placeholder or missing brief fields."
    )


def test_build_design_brief_scope_matrix_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_scope_matrix(store, "dbf-missing") is None
    finally:
        store.close()
