"""Tests for design brief outreach pack generation."""

from __future__ import annotations

import csv
import io
import json

from max.analysis.design_brief_outreach_pack import (
    OUTREACH_PACK_CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_outreach_pack,
    render_design_brief_outreach_pack,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_outreach_pack_sections_and_templates(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        pack = build_design_brief_outreach_pack(store, brief_id)
    finally:
        store.close()

    assert pack is not None
    assert pack["schema_version"] == SCHEMA_VERSION
    assert pack["kind"] == "max.design_brief.outreach_pack"
    assert pack["design_brief"]["id"] == brief_id
    assert pack["summary"]["buyer"] == "engineering manager"
    assert pack["summary"]["specific_user"] == "platform engineer"
    assert pack["summary"]["fallbacks_used"] == []
    assert [segment["id"] for segment in pack["target_segments"]] == [
        "primary_workflow_owner",
        "economic_sponsors",
        "adjacent_evaluators",
    ]
    assert [template["id"] for template in pack["templates"]] == [
        "email_primary_user",
        "dm_sponsor",
        "warm_intro",
    ]
    assert len(pack["qualification_questions"]) == 6
    assert len(pack["follow_up_artifacts"]) == 3
    assert any(
        objection["id"] == "risk_or_trust" and "Security review" in objection["objection"]
        for objection in pack["objection_handling"]
    )
    assert json.loads(json.dumps(pack))["design_brief"]["id"] == brief_id


def test_build_design_brief_outreach_pack_uses_explicit_fallbacks(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        pack = build_design_brief_outreach_pack(store, brief_id)
    finally:
        store.close()

    assert pack is not None
    assert pack["summary"]["buyer"] == "economic buyer (fallback: missing buyer)"
    assert pack["summary"]["specific_user"] == "target user (fallback: missing specific_user)"
    assert pack["summary"]["workflow_context"] == "target workflow (fallback: missing workflow_context)"
    assert pack["summary"]["fallbacks_used"] == ["buyer", "specific_user", "workflow_context"]
    assert pack["target_segments"][0]["buyer"] == "economic buyer (fallback: missing buyer)"
    assert "target workflow (fallback: missing workflow_context)" in pack["templates"][0]["subject"]


def test_render_design_brief_outreach_pack_markdown(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        pack = build_design_brief_outreach_pack(store, brief_id)
    finally:
        store.close()

    assert pack is not None
    markdown = render_design_brief_outreach_pack(pack, fmt="markdown")

    assert markdown.startswith("# Outreach Pack: Outreach Pack Brief")
    assert "## Target Segments" in markdown
    assert "## Outreach Hypotheses" in markdown
    assert "## Templates" in markdown
    assert "## Objection Handling" in markdown
    assert "## Qualification Questions" in markdown
    assert "## Follow-up Steps" in markdown
    assert "### Primary User Email" in markdown
    assert f"Design brief: `{brief_id}`" in markdown


def test_render_design_brief_outreach_pack_csv_headers_sections_and_rows(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        pack = build_design_brief_outreach_pack(store, brief_id)
    finally:
        store.close()

    assert pack is not None
    csv_text = render_design_brief_outreach_pack(pack, fmt="csv")
    repeated = render_design_brief_outreach_pack(pack, fmt="csv")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(OUTREACH_PACK_CSV_COLUMNS)
    assert reader.fieldnames == list(OUTREACH_PACK_CSV_COLUMNS)
    assert [row["section"] for row in rows] == [
        *(["target_segments"] * 3),
        *(["outreach_hypotheses"] * 3),
        *(["templates"] * 3),
        *(["objection_handling"] * 3),
        *(["qualification_questions"] * 6),
        *(["follow_up_artifacts"] * 3),
    ]
    assert [row["order"] for row in rows[:3]] == ["1", "2", "3"]

    first_segment = rows[0]
    assert first_segment["type"] == "segment"
    assert first_segment["id"] == "primary_workflow_owner"
    assert first_segment["title_name"] == "Primary workflow owners"
    assert "Recruiting angle: Validate whether" in first_segment["body_detail"]
    assert first_segment["evidence_source_idea_ids"] == "bu-outreach-lead;bu-outreach-support"
    assert first_segment["design_brief_id"] == brief_id
    assert first_segment["design_brief_title"] == "Outreach Pack Brief"
    assert first_segment["buyer"] == "engineering manager"
    assert first_segment["specific_user"] == "platform engineer"
    assert first_segment["workflow_context"] == "pilot intake workflow"

    template = rows[6]
    assert template["section"] == "templates"
    assert template["type"] == "template"
    assert template["id"] == "email_primary_user"
    assert template["channel_stage"] == "email"
    assert "Subject: Question about pilot intake workflow" in template["body_detail"]
    assert template["cta"] == "Ask for a 20 minute discovery call this week."

    question = rows[12]
    assert question["section"] == "qualification_questions"
    assert question["type"] == "qualification_question"
    assert question["channel_stage"] == "fit"
    assert "Who owns pilot intake workflow today" in question["body_detail"]

    follow_up = rows[-1]
    assert follow_up["section"] == "follow_up_artifacts"
    assert follow_up["type"] == "follow_up_artifact"
    assert follow_up["title_name"] == "No-response follow-up"
    assert follow_up["channel_stage"] == "3 to 5 business days after first outreach"


def test_build_design_brief_outreach_pack_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_outreach_pack.db"), wal_mode=True)
    try:
        pack = build_design_brief_outreach_pack(store, "dbf-missing")
    finally:
        store.close()

    assert pack is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_outreach_pack.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-outreach-lead",
        title="Outreach Pack Lead",
        one_liner="Recruit validation pilots from persisted design briefs.",
        category="application",
        problem="Validated ideas need concrete recruiting actions.",
        solution="Generate deterministic outreach packs.",
        value_proposition="Turn design briefs into pilot recruiting motion.",
        specific_user="platform engineer",
        buyer="engineering manager",
        workflow_context="pilot intake workflow",
        current_workaround="manual spreadsheet tracking",
        why_now="Validated specs need customer discovery.",
        validation_plan="Interview five workflow owners and recruit two pilots.",
        first_10_customers="developer platform teams",
        domain_risks=["Security review can delay pilots."],
        tech_approach="Python export module and CLI command.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-outreach-support",
        title="Outreach Pack Support",
        one_liner="Track sponsor questions for pilot recruiting.",
        category="application",
        problem="Pilot discovery loses sponsor context.",
        solution="Persist qualification and follow-up artifacts.",
        value_proposition="Make pilot readiness auditable.",
        specific_user="product operator",
        buyer="product lead",
        workflow_context="customer discovery handoff",
        domain_risks=["Recruiting messages may target the wrong owner."],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Outreach Pack Brief",
            domain="developer-tools",
            theme="pilot-recruiting",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=88.0,
            why_this_now="Validation plans need pilot recruiting.",
            merged_product_concept="An outreach pack export for persisted design briefs.",
            synthesis_rationale="Completes customer discovery handoff.",
            mvp_scope=["JSON outreach pack", "Markdown outreach pack"],
            first_milestones=["Recruit first pilot"],
            validation_plan="Run discovery calls with five teams.",
            risks=["Security review can delay pilots."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_outreach_pack.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-outreach-sparse",
        title="Sparse Outreach Lead",
        one_liner="Recruit pilots with incomplete audience fields.",
        category="application",
        problem="Audience context is incomplete.",
        solution="Use explicit fallback recruiting language.",
        value_proposition="Keep outreach deterministic even with missing buyer and user fields.",
        validation_plan="Ask discovery calls to identify buyer, user, and workflow.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Outreach Brief",
            domain="developer-tools",
            theme="pilot-recruiting",
            lead=Candidate(unit=lead),
            readiness_score=52.0,
            why_this_now="The team needs discovery before build expansion.",
            merged_product_concept="A sparse outreach pack.",
            synthesis_rationale="Tests explicit fallbacks.",
            mvp_scope=["Fallback-aware outreach"],
            first_milestones=["Identify buyer and user"],
            validation_plan="Interview teams to fill missing audience fields.",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
    return store, brief_id
