from __future__ import annotations

import csv
from io import StringIO
import json

import pytest

from max.analysis.design_brief_prd import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_prd,
    render_design_brief_prd,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _unit(
    unit_id: str,
    *,
    evidence_signals: list[str] | None = None,
    inspiring_insights: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="PRD Source Idea",
        one_liner="Export a design brief as a one-page PRD",
        category="application",
        problem="Product and design agents need compact handoff artifacts.",
        solution="Generate a deterministic PRD from persisted design briefs.",
        value_proposition="Move from signal to spec without re-summarizing context.",
        specific_user="product designer",
        buyer="head of product",
        workflow_context="design brief handoff",
        current_workaround="manual PRD drafting",
        why_now="Persisted design briefs already contain planning context.",
        validation_plan="Review the PRD with product and design agents.",
        domain_risks=["Evidence references may be omitted from handoffs."],
        evidence_rationale="A linked source signal describes PRD handoff demand.",
        evidence_signals=evidence_signals or [],
        inspiring_insights=inspiring_insights or [],
        tech_approach="FastAPI endpoint backed by a deterministic renderer.",
        suggested_stack={"api": "fastapi", "format": "markdown"},
        domain="developer-tools",
        status="approved",
    )


def _seed_brief(store: Store) -> str:
    signal = Signal(
        id="sig-prd-handoff",
        source_type=SignalSourceType.ARTICLE,
        source_adapter="test",
        title="Teams want concise PRD handoffs",
        content="A compact PRD helps downstream product and design planning.",
        url="https://example.com/prd-handoff",
        metadata={"signal_role": "problem"},
    )
    store.insert_signal(signal)
    lead = _unit(
        "bu-prd-lead",
        evidence_signals=[signal.id],
        inspiring_insights=["ins-prd-1"],
    )
    support = _unit("bu-prd-support")
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    return store.insert_design_brief(
        ProjectBrief(
            title="PRD Export Brief",
            domain="developer-tools",
            theme="handoff-export",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=86.0,
            why_this_now="Teams need design briefs to become product specifications.",
            merged_product_concept="A deterministic one-page PRD export.",
            synthesis_rationale="Combines persisted brief context with source idea evidence.",
            mvp_scope=["Structured PRD endpoint", "Markdown PRD export"],
            first_milestones=["Return required PRD sections"],
            validation_plan="Validate the PRD with product and design agents.",
            risks=["PRD sections may become too verbose."],
            source_idea_ids=["bu-prd-lead", "bu-prd-support"],
        )
    )


def test_build_design_brief_prd_returns_required_sections_and_traceability(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        prd = build_design_brief_prd(store, brief_id)
    finally:
        store.close()

    assert prd is not None
    assert prd["schema_version"] == SCHEMA_VERSION
    assert set(prd["sections"]) == {
        "title",
        "user_buyer",
        "problem",
        "proposed_workflow",
        "non_goals",
        "success_metrics",
        "mvp_scope",
        "dependencies",
        "risks",
        "evidence_links",
    }
    assert prd["design_brief"]["source_idea_ids"] == ["bu-prd-lead", "bu-prd-support"]
    assert "bu-prd-lead" in prd["sections"]["problem"]["source_idea_ids"]


def test_build_design_brief_prd_includes_source_idea_evidence(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        prd = build_design_brief_prd(store, brief_id)
    finally:
        store.close()

    assert prd is not None
    evidence = "\n".join(prd["sections"]["evidence_links"]["content"])
    assert "sig-prd-handoff" in evidence
    assert "https://example.com/prd-handoff" in evidence
    assert "ins-prd-1" in evidence


def test_build_design_brief_prd_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_prd(store, "dbf-missing") is None
    finally:
        store.close()


def test_render_design_brief_prd_json_and_markdown(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        prd = build_design_brief_prd(store, brief_id)
    finally:
        store.close()

    assert prd is not None
    parsed = json.loads(render_design_brief_prd(prd, "json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_prd(prd, "markdown")
    assert markdown.startswith("# PRD: PRD Export Brief")
    assert "Schema: `max.design_brief.prd.v1`" in markdown
    assert "## User / Buyer" in markdown
    assert "## Evidence Links" in markdown
    assert "https://example.com/prd-handoff" in markdown

    with pytest.raises(ValueError):
        render_design_brief_prd(prd, "yaml")


def test_render_design_brief_prd_csv_includes_metadata_sections_and_traceability(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        prd = build_design_brief_prd(store, brief_id)
    finally:
        store.close()

    assert prd is not None
    rendered = render_design_brief_prd(prd, "csv")
    rows = list(csv.DictReader(StringIO(rendered)))

    assert rendered.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows
    assert rows[0]["schema_version"] == SCHEMA_VERSION
    assert rows[0]["design_brief_title"] == "PRD Export Brief"
    assert rows[0]["domain"] == "developer-tools"
    assert rows[0]["theme"] == "handoff-export"
    assert rows[0]["readiness_score"] == "86.0"

    problem_row = next(row for row in rows if row["section_key"] == "problem")
    assert problem_row["item_type"] == "section"
    assert problem_row["item_id"] == "problem"
    assert problem_row["priority"] == "high"
    assert problem_row["source_idea_ids"] == "bu-prd-lead; bu-prd-support"
    assert problem_row["evidence_ids"] == "sig-prd-handoff; ins-prd-1"

    mvp_rows = [row for row in rows if row["section_key"] == "mvp_scope"]
    assert [row["item_id"] for row in mvp_rows] == ["mvp_scope:1", "mvp_scope:2"]
    assert [row["description"] for row in mvp_rows] == [
        "Structured PRD endpoint",
        "Markdown PRD export",
    ]

    evidence_rows = [row for row in rows if row["section_key"] == "evidence_links"]
    assert {row["item_title"] for row in evidence_rows} >= {"sig-prd-handoff", "ins-prd-1"}
    assert any("https://example.com/prd-handoff" in row["detail"] for row in evidence_rows)


def test_render_design_brief_prd_csv_is_deterministic(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        prd = build_design_brief_prd(store, brief_id)
    finally:
        store.close()

    assert prd is not None
    assert render_design_brief_prd(prd, "csv") == render_design_brief_prd(prd, "csv")


def test_render_design_brief_prd_csv_escapes_special_characters(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        prd = build_design_brief_prd(store, brief_id)
    finally:
        store.close()

    assert prd is not None
    prd["sections"]["problem"]["content"] = 'Problem has "quoted", comma\nand newline'
    rendered = render_design_brief_prd(prd, "csv")
    rows = list(csv.DictReader(StringIO(rendered)))

    assert '"Problem has ""quoted"", comma\nand newline"' in rendered
    problem_row = next(row for row in rows if row["section_key"] == "problem")
    assert problem_row["description"] == 'Problem has "quoted", comma\nand newline'


def test_render_design_brief_prd_csv_empty_sections_writes_header_only() -> None:
    prd = {
        "schema_version": SCHEMA_VERSION,
        "design_brief": {
            "id": "dbf-empty",
            "title": "Empty PRD",
            "domain": "",
            "theme": "",
            "readiness_score": 0.0,
            "design_status": "",
            "lead_idea_id": "",
            "source_idea_ids": [],
        },
        "sections": {
            "mvp_scope": {
                "heading": "MVP Scope",
                "content": [],
                "source_fields": ["mvp_scope"],
                "source_idea_ids": [],
            },
            "problem": {
                "heading": "Problem",
                "content": "",
                "source_fields": ["problem"],
                "source_idea_ids": [],
            },
        },
        "source_ideas": [],
    }

    rendered = render_design_brief_prd(prd, "csv")

    assert rendered == ",".join(CSV_COLUMNS) + "\n"
    assert list(csv.DictReader(StringIO(rendered))) == []


def test_render_design_brief_prd_csv_rejects_invalid_format(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        prd = build_design_brief_prd(store, brief_id)
    finally:
        store.close()

    assert prd is not None
    with pytest.raises(ValueError):
        render_design_brief_prd(prd, "xml")
