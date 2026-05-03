"""Tests for design brief customer journey map generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_customer_journey_map import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_customer_journey_map,
    customer_journey_map_filename,
    render_design_brief_customer_journey_map,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_customer_journey_map_translates_persisted_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_journey_map(store, brief_id)
        repeated = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.customer_journey_map"
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["target_user"] == "customer operations manager"
    assert report["summary"]["buyer"] == "customer success director"
    assert report["summary"]["workflow_context"] == "approved pilot onboarding"
    assert report["summary"]["current_workaround"] == "manual kickoff notes"
    assert report["summary"]["fallbacks_used"] == []
    assert [stage["id"] for stage in report["journey_stages"]] == [
        "JM1",
        "JM2",
        "JM3",
        "JM4",
        "JM5",
    ]
    assert [stage["name"] for stage in report["journey_stages"]] == [
        "Problem Awareness",
        "Solution Evaluation",
        "First Use",
        "Repeat Adoption",
        "Expansion Decision",
    ]
    assert all(
        {
            "user_goals",
            "touchpoints",
            "friction_points",
            "success_signals",
            "owner",
            "source_idea_ids",
        }
        <= set(stage)
        for stage in report["journey_stages"]
    )
    assert all(
        stage["source_idea_ids"] == ["bu-journey-lead", "bu-journey-support"]
        for stage in report["journey_stages"]
    )
    assert report["journey_stages"][0]["owner"] == "Product marketing owner"
    assert "design_brief.why_this_now" in report["journey_stages"][0]["evidence_reference_ids"]
    assert any("Privacy approval" in point for point in report["journey_stages"][2]["friction_points"])
    assert {reference["id"] for reference in report["evidence_references"]} >= {
        "design_brief.why_this_now",
        "design_brief.synthesis_rationale",
        "design_brief.validation_plan",
        "sig-journey",
        "ins-journey",
        "sig-support",
    }
    assert report["readiness_warnings"] == []
    assert [idea["id"] for idea in report["source_ideas"]] == ["bu-journey-lead", "bu-journey-support"]
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_build_design_brief_customer_journey_map_sparse_brief_uses_fallbacks(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "design_brief_customer_journey_map_sparse.db"), wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-journey-sparse",
            title="Sparse Journey Source",
            one_liner="Sparse source idea for fallback journey mapping.",
            category="application",
            problem="",
            solution="",
            value_proposition="",
            specific_user="",
            buyer="",
            workflow_context="",
            current_workaround="",
            why_now="",
            validation_plan="",
            first_10_customers="",
            domain_risks=[],
            evidence_signals=[],
            inspiring_insights=[],
            tech_approach="",
            suggested_stack={},
            domain="",
            status="draft",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Sparse Journey Brief",
                domain="",
                theme="",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=44.0,
                why_this_now="",
                merged_product_concept="",
                synthesis_rationale="",
                mvp_scope=[],
                first_milestones=[],
                validation_plan="",
                risks=[],
                source_idea_ids=[lead.id],
                design_status="draft",
            )
        )
        report = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["target_user"] == "Sparse Journey Brief user"
    assert report["summary"]["buyer"] == "customer sponsor"
    assert report["summary"]["workflow_context"] == "Sparse Journey Brief workflow"
    assert report["summary"]["current_workaround"] == "manual or ad hoc workflow"
    assert report["summary"]["value_proposition"] == (
        "Help Sparse Journey Brief user improve Sparse Journey Brief workflow."
    )
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "current_workaround",
        "value_proposition",
    ]
    assert report["journey_stages"][0]["source_idea_ids"] == ["bu-journey-sparse"]
    assert report["journey_stages"][0]["user_goals"]
    assert report["evidence_references"] == []
    assert [warning["severity"] for warning in report["readiness_warnings"]] == [
        "high",
        "high",
        "medium",
        "medium",
        "medium",
        "medium",
        "medium",
        "medium",
    ]


def test_render_design_brief_customer_journey_map_markdown_json_and_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_customer_journey_map(report, fmt="markdown")
    assert markdown.startswith("# Customer Journey Map: Customer Journey Map Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Journey Context" in markdown
    assert "## Journey Stages" in markdown
    assert "### 1. Problem Awareness" in markdown
    assert "### 3. First Use" in markdown
    assert "- User goals:" in markdown
    assert "- Touchpoints:" in markdown
    assert "- Friction points:" in markdown
    assert "- Success signals:" in markdown
    assert "## Evidence References" in markdown
    assert "**sig-journey**" in markdown
    assert "## Readiness Warnings" in markdown

    rendered_json = render_design_brief_customer_journey_map(report, fmt="json")
    assert json.loads(rendered_json) == report

    with pytest.raises(ValueError, match="Unsupported customer journey map format: yaml"):
        render_design_brief_customer_journey_map(report, fmt="yaml")


def test_render_design_brief_customer_journey_map_csv_rows_and_filename(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_customer_journey_map(report, fmt="csv")
    repeated = render_design_brief_customer_journey_map(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert set(rows[0]) == set(CSV_COLUMNS)
    assert len(rows) == 5 + (3 * 5) + (2 * 5) + (2 * 5) + (2 * 5)
    assert [row["section"] for row in rows[:8]] == [
        "journey_stages",
        "touchpoints",
        "touchpoints",
        "touchpoints",
        "pain_points",
        "pain_points",
        "opportunities",
        "metrics",
    ]
    assert [row["stage_id"] for row in rows if row["row_type"] == "stage"] == [
        "JM1",
        "JM2",
        "JM3",
        "JM4",
        "JM5",
    ]
    assert [row["stage_sequence"] for row in rows if row["row_type"] == "stage"] == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[0]["design_brief_title"] == "Customer Journey Map Brief"
    assert rows[0]["readiness_score"] == "88.0"
    assert rows[0]["design_status"] == "approved"
    assert rows[0]["stage_name"] == "Problem Awareness"
    assert rows[0]["stage_owner"] == "Product marketing owner"
    assert rows[1]["row_type"] == "touchpoint"
    assert rows[1]["item_id"] == "JM1-T1"
    assert rows[1]["item_value"] == "problem narrative"
    assert rows[4]["row_type"] == "pain_point"
    assert rows[4]["item_id"] == "JM1-P1"
    assert rows[6]["row_type"] == "opportunity"
    assert rows[7]["row_type"] == "metric"
    assert rows[7]["item_value"] == "Target user can restate the problem in their own words."
    assert json.loads(rows[0]["evidence_reference_ids"])[0] == "design_brief.why_this_now"
    assert json.loads(rows[0]["source_idea_ids"]) == ["bu-journey-lead", "bu-journey-support"]
    assert customer_journey_map_filename(report["design_brief"], fmt="csv").endswith(".csv")


def test_render_design_brief_customer_journey_map_csv_sorts_by_sequence() -> None:
    report = {
        "design_brief": {
            "id": "dbf-journey-csv",
            "title": "Journey CSV",
            "readiness_score": 72.5,
            "source_idea_ids": ["fallback-source"],
        },
        "journey_stages": [
            {
                "id": "JM2",
                "sequence": 2,
                "name": "Second",
                "owner": "Owner B",
                "user_goals": ["second goal"],
                "touchpoints": ["second touchpoint"],
                "friction_points": ["second friction"],
                "success_signals": ["second signal"],
                "evidence_reference_ids": ["evidence-2"],
                "source_idea_ids": ["source-2"],
            },
            {
                "id": "JM1",
                "sequence": 1,
                "name": "First",
                "owner": "Owner A",
                "user_goals": ["first goal"],
                "touchpoints": ["first touchpoint"],
                "friction_points": ["first friction"],
                "success_signals": ["first signal"],
                "evidence_reference_ids": ["evidence-1"],
                "source_idea_ids": [],
            },
        ],
    }

    rows = list(
        csv.DictReader(io.StringIO(render_design_brief_customer_journey_map(report, fmt="csv")))
    )

    assert [(row["stage_sequence"], row["stage_id"], row["row_type"]) for row in rows] == [
        ("1", "JM1", "stage"),
        ("1", "JM1", "touchpoint"),
        ("1", "JM1", "pain_point"),
        ("1", "JM1", "opportunity"),
        ("1", "JM1", "metric"),
        ("2", "JM2", "stage"),
        ("2", "JM2", "touchpoint"),
        ("2", "JM2", "pain_point"),
        ("2", "JM2", "opportunity"),
        ("2", "JM2", "metric"),
    ]
    assert json.loads(rows[0]["source_idea_ids"]) == ["fallback-source"]
    assert json.loads(rows[5]["source_idea_ids"]) == ["source-2"]


def test_render_design_brief_customer_journey_map_csv_escapes_special_characters(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_journey_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["design_brief"]["title"] = 'Journey, "CSV"\nBrief'
    report["summary"]["journey_goal"] = 'Map, "quoted"\njourney'
    report["journey_stages"][0]["name"] = 'Awareness, "Stage"\nName'
    report["journey_stages"][0]["touchpoints"][0] = 'Touch, "point"\nline two'

    first = render_design_brief_customer_journey_map(report, fmt="csv")
    second = render_design_brief_customer_journey_map(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(first)))

    assert first == second
    assert '"Journey, ""CSV""\nBrief"' in first
    assert '"Awareness, ""Stage""\nName"' in first
    touchpoint = next(row for row in rows if row["item_id"] == "JM1-T1")
    assert touchpoint["design_brief_title"] == 'Journey, "CSV"\nBrief'
    assert touchpoint["stage_name"] == 'Awareness, "Stage"\nName'
    assert touchpoint["item_value"] == 'Touch, "point"\nline two'


def test_render_design_brief_customer_journey_map_csv_sparse_stage() -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.customer_journey_map",
        "design_brief": {
            "id": "dbf-sparse",
            "title": "Sparse CSV",
            "readiness_score": 15.0,
            "design_status": "draft",
            "source_idea_ids": ["source-a"],
        },
        "summary": {
            "journey_goal": "Map sparse journey.",
            "target_user": "operator",
            "buyer": "sponsor",
            "workflow_context": "review workflow",
        },
        "journey_stages": [
            {
                "id": "JM1",
                "sequence": 1,
                "name": "Only Stage",
                "owner": "Product lead",
                "user_goals": [],
                "touchpoints": [],
                "friction_points": [],
                "success_signals": [],
                "evidence_reference_ids": [],
                "source_idea_ids": [],
            }
        ],
    }

    rows = list(
        csv.DictReader(io.StringIO(render_design_brief_customer_journey_map(report, fmt="csv")))
    )

    assert len(rows) == 1
    assert rows[0]["row_type"] == "stage"
    assert rows[0]["stage_id"] == "JM1"
    assert rows[0]["item_value"] == "Only Stage"
    assert rows[0]["evidence_reference_ids"] == ""
    assert json.loads(rows[0]["source_idea_ids"]) == ["source-a"]


def test_build_design_brief_customer_journey_map_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_customer_journey_map.db"), wal_mode=True)
    try:
        report = build_design_brief_customer_journey_map(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_customer_journey_map.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-journey-lead",
        title="Journey Map Lead",
        one_liner="Turn approved pilots into traceable adoption journeys.",
        category="application",
        problem="Validated ideas lack a user adoption path after design brief approval.",
        solution="Export deterministic customer journey maps from design briefs.",
        value_proposition="Make adoption planning concrete for customer-facing teams.",
        specific_user="customer operations manager",
        buyer="customer success director",
        workflow_context="approved pilot onboarding",
        current_workaround="manual kickoff notes",
        why_now="Pilot approvals need customer journey planning before rollout.",
        validation_plan="Track first value, repeat usage, sponsor acceptance, and expansion readiness.",
        first_10_customers="customer success teams managing pilot graduates",
        domain_risks=["Privacy approval can block customer data setup."],
        evidence_signals=["sig-journey"],
        inspiring_insights=["ins-journey"],
        tech_approach="Python export module.",
        suggested_stack={"language": "python"},
        domain="customer-success",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-journey-support",
        title="Journey Map Support",
        one_liner="Capture repeat adoption touchpoints for pilot customers.",
        category="application",
        problem="Teams stop after first use without repeat adoption evidence.",
        solution="Add journey stages with touchpoints and success signals.",
        value_proposition="Help teams understand adoption friction after first use.",
        specific_user="customer champion",
        buyer="product lead",
        workflow_context="repeat pilot rollout",
        current_workaround="ad hoc follow-up emails",
        validation_plan="Confirm repeat usage and support handoff.",
        domain_risks=["Champion handoff may not happen before expansion review."],
        evidence_signals=["sig-support"],
        domain="customer-success",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Customer Journey Map Brief",
            domain="customer-success",
            theme="adoption-planning",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=88.0,
            why_this_now="Generated project specs need customer journey artifacts.",
            merged_product_concept="A customer journey map export for persisted design briefs.",
            synthesis_rationale="Connects pilot approval to adoption planning and expansion decisions.",
            mvp_scope=["Journey map JSON", "Journey map Markdown"],
            first_milestones=["Complete guided first-value journey"],
            validation_plan="Confirm customer teams can repeat the workflow without concierge help.",
            risks=["Privacy approval can block customer data setup."],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )
    return store, brief_id
