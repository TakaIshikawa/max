"""Tests for design brief rollout communications plan generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_rollout_comms_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_rollout_comms_plan,
    render_design_brief_rollout_comms_plan,
    rollout_comms_plan_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_rollout_comms_plan_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_rollout_comms_plan(store, brief_id)
        repeated = build_design_brief_rollout_comms_plan(store, brief_id)
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
    assert [audience["id"] for audience in report["target_audiences"]] == [
        "internal_product_engineering",
        "internal_sales_success_support",
        "pilot_customers",
        "external_market",
    ]
    assert [phase["id"] for phase in report["launch_phases"]] == [
        "prep",
        "internal_enablement",
        "controlled_launch",
        "broad_announcement",
        "post_launch_followup",
    ]
    assert [row["id"] for row in report["channel_message_matrix"]] == [
        f"RCM{index}" for index in range(1, 7)
    ]
    assert len(report["internal_enablement_notes"]) == 3
    assert len(report["customer_facing_announcement_drafts"]) == 2
    assert any(hook["id"] == "FAQ1" and "Audit concerns" in hook["question"] for hook in report["risk_faq_hooks"])
    assert any(item["id"] == "sig-rollout-1" for item in report["evidence_references"])
    assert report["readiness_warnings"] == []
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_render_design_brief_rollout_comms_plan_markdown_and_json(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_rollout_comms_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_rollout_comms_plan(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_rollout_comms_plan(report, fmt="markdown")
    repeated = render_design_brief_rollout_comms_plan(report, fmt="markdown")
    assert markdown.startswith("# Rollout Communications Plan: Rollout Comms Brief")
    assert markdown.endswith("\n")
    assert markdown == repeated
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Audience Segments" in markdown
    assert "## Launch Sequence" in markdown
    assert "## Timing And Owners" in markdown
    assert "## Approval Checkpoints" in markdown
    assert "## Feedback Loops" in markdown
    assert "| Phase | Audience | Channel | Owner | Message | CTA |" in markdown
    assert "## Internal Enablement Notes" in markdown
    assert "## Customer-Facing Announcement Drafts" in markdown
    assert "## Risk and FAQ Hooks" in markdown
    assert "## Evidence References" in markdown
    assert "## Readiness Warnings" in markdown


def test_render_design_brief_rollout_comms_plan_markdown_rows_and_details(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_rollout_comms_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_rollout_comms_plan(report, fmt="markdown")

    assert (
        "| Internal product and engineering | internal | Understand scope, owner handoffs, "
        "validation gates, and rollback triggers. | Focus rollout on Audience-specific "
        "messaging. | launch brief, engineering sync |"
    ) in markdown
    assert (
        "| Controlled customer launch | Pilot customers | email | Customer success lead | "
        f"{report['channel_message_matrix'][2]['message']} | Join the controlled rollout "
        "and share first-use feedback. |"
    ) in markdown
    assert (
        "| 3. Controlled customer launch | T day through T+5 business days | "
        "Customer success lead | Invite the first cohort to try Audience-specific messaging. | "
        "Review messaging with two pilot teams before broad announcement. |"
    ) in markdown
    assert (
        "- **Controlled customer launch**: T day through T+5 business days\n"
        "  Owner: Customer success lead"
    ) in markdown
    assert (
        "- **Prep and message lock** (Product lead): Launch gate is "
        "`ready_for_launch_review` and draft messages are approved."
    ) in markdown
    assert (
        "| Controlled customer launch | Pilot customers | email | Customer success lead | "
        "Join the controlled rollout and share first-use feedback. |"
    ) in markdown
    assert brief_id


def test_render_design_brief_rollout_comms_plan_markdown_empty_fallbacks() -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "design_brief": {
            "id": "dbf-empty",
            "title": "Empty Rollout",
            "readiness_score": 0,
            "source_idea_ids": [],
        },
        "summary": {},
    }

    markdown = render_design_brief_rollout_comms_plan(report, fmt="markdown")

    assert markdown.endswith("\n")
    assert "Design brief: `dbf-empty`" in markdown
    assert "| None | unknown | Not specified | Not specified | none |" in markdown
    assert "| None | Not scheduled | Unassigned | Not specified | Not specified |" in markdown
    assert (
        "| None | Not specified | Not specified | Unassigned | Not specified | Not specified |"
        in markdown
    )
    assert "| None | Not specified | Not specified | Unassigned | Not specified |" in markdown
    assert markdown.count("- None") >= 5


def test_render_design_brief_rollout_comms_plan_csv_rows_and_order(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_rollout_comms_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_rollout_comms_plan(report, fmt="csv")
    repeated = render_design_brief_rollout_comms_plan(report, fmt="csv")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [row["section"] for row in rows] == (
        ["target_audiences"] * len(report["target_audiences"])
        + ["launch_phases"] * len(report["launch_phases"])
        + ["channel_message_matrix"] * len(report["channel_message_matrix"])
        + ["internal_enablement_notes"] * len(report["internal_enablement_notes"])
        + ["customer_facing_announcement_drafts"]
        * len(report["customer_facing_announcement_drafts"])
        + ["risk_faq_hooks"] * len(report["risk_faq_hooks"])
    )
    assert [row["item_id"] for row in rows[:4]] == [
        "internal_product_engineering",
        "internal_sales_success_support",
        "pilot_customers",
        "external_market",
    ]
    assert [row["item_id"] for row in rows[4:9]] == [
        "prep",
        "internal_enablement",
        "controlled_launch",
        "broad_announcement",
        "post_launch_followup",
    ]

    matrix_row = next(row for row in rows if row["item_id"] == "RCM3")
    assert matrix_row["design_brief_id"] == brief_id
    assert matrix_row["design_brief_title"] == "Rollout Comms Brief"
    assert matrix_row["audience"] == "Pilot customers"
    assert matrix_row["channel"] == "email"
    assert matrix_row["timing"] == "Controlled customer launch"
    assert matrix_row["owner"] == "Customer success lead"
    assert matrix_row["message"] == report["channel_message_matrix"][2]["message"]
    assert matrix_row["call_to_action"] == "Join the controlled rollout and share first-use feedback."


def test_render_design_brief_rollout_comms_plan_csv_compact_details(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_rollout_comms_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rows = list(
        csv.DictReader(io.StringIO(render_design_brief_rollout_comms_plan(report, fmt="csv")))
    )

    audience_row = rows[0]
    matrix_row = next(row for row in rows if row["item_id"] == "RCM1")
    draft_row = next(row for row in rows if row["item_id"] == "CFA1")

    assert audience_row["channel"] == '["launch brief","engineering sync"]'
    assert json.loads(audience_row["details"]) == {
        "need": "Understand scope, owner handoffs, validation gates, and rollback triggers.",
        "source_idea_ids": ["bu-rollout-lead", "bu-rollout-support"],
        "type": "internal",
    }
    assert audience_row["details"] == (
        '{"need":"Understand scope, owner handoffs, validation gates, and rollback triggers.",'
        '"source_idea_ids":["bu-rollout-lead","bu-rollout-support"],"type":"internal"}'
    )
    assert json.loads(matrix_row["details"])["source_fields"] == [
        "mvp_scope",
        "workflow_context",
        "merged_product_concept",
    ]
    assert draft_row["details"] == json.dumps(
        json.loads(draft_row["details"]), sort_keys=True, separators=(",", ":")
    )
    assert brief_id


def test_rollout_comms_plan_weak_readiness_warnings(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_rollout_comms_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == ["buyer", "specific_user", "workflow_context"]
    assert report["summary"]["readiness_warning_count"] == 5
    warnings = [warning["warning"] for warning in report["readiness_warnings"]]
    assert any("Readiness score is 42.0/100" in warning for warning in warnings)
    assert any("Design status is `candidate`" in warning for warning in warnings)
    assert any("Missing buyer" in warning for warning in warnings)
    assert report["target_audiences"][2]["message_angle"].startswith("Help Sparse Rollout Brief user")


def test_rollout_comms_plan_filename_generation() -> None:
    design_brief = {"id": "dbf-123", "title": "Rollout Comms: Plan / Alpha"}

    assert (
        rollout_comms_plan_filename(design_brief)
        == "dbf-123-Rollout-Comms-Plan-Alpha-rollout-comms-plan.md"
    )
    assert (
        rollout_comms_plan_filename(design_brief, fmt="json")
        == "dbf-123-Rollout-Comms-Plan-Alpha-rollout-comms-plan.json"
    )
    assert (
        rollout_comms_plan_filename(design_brief, fmt="csv")
        == "dbf-123-Rollout-Comms-Plan-Alpha-rollout-comms-plan.csv"
    )


def test_rollout_comms_plan_missing_brief_and_invalid_format(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_rollout_comms.db"), wal_mode=True)
    try:
        assert build_design_brief_rollout_comms_plan(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported rollout communications plan format: yaml"):
        render_design_brief_rollout_comms_plan({"design_brief": {}}, fmt="yaml")


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_rollout_comms.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-rollout-lead",
        title="Rollout Comms Lead",
        one_liner="Coordinate rollout communication across launch audiences.",
        category="application",
        problem="Design launches lack a consistent communications package.",
        solution="Generate audience-specific rollout messages from persisted briefs.",
        value_proposition="Make rollout coordination explicit and repeatable.",
        specific_user="platform lead",
        buyer="engineering director",
        workflow_context="internal developer platform rollout",
        current_workaround="manual launch docs",
        why_now="Design briefs already carry launch and validation inputs.",
        validation_plan="Review messaging with two pilot teams before broad announcement.",
        first_10_customers="developer platform teams",
        domain_risks=["Audit concerns can block external announcement."],
        evidence_signals=["sig-rollout-1"],
        inspiring_insights=["ins-rollout-1"],
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-rollout-support",
        title="Rollout Comms Support",
        one_liner="Prepare enablement notes for success and support.",
        category="application",
        problem="Customer-facing teams need launch sequencing.",
        solution="Attach phases, messages, and FAQ hooks to the brief.",
        value_proposition="Give sales, success, and support shared rollout language.",
        specific_user="customer success manager",
        buyer="support director",
        workflow_context="customer launch handoff",
        domain_risks=["Support capacity may be unclear."],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Rollout Comms Brief",
            domain="developer-tools",
            theme="rollout-comms",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=84.0,
            why_this_now="Validation and launch mechanics need a communication package.",
            merged_product_concept="A deterministic rollout communications plan for persisted design briefs.",
            synthesis_rationale="Completes the launch handoff for internal and external audiences.",
            mvp_scope=["Audience-specific messaging", "Launch phase sequencing"],
            first_milestones=["Publish internal enablement note", "Send pilot customer announcement"],
            validation_plan="Review messaging with two pilot teams before broad announcement.",
            risks=["Audit concerns can block external announcement."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_rollout_comms.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-rollout-sparse",
        title="Sparse Rollout Lead",
        one_liner="Create rollout comms with weak audience context.",
        category="application",
        problem="Rollout input is incomplete.",
        solution="Use deterministic fallback messaging.",
        value_proposition="Keep communication planning moving while gaps are visible.",
        validation_plan="Validate fallback messages with internal reviewers.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Rollout Brief",
            domain="developer-tools",
            theme="rollout-comms",
            lead=Candidate(unit=lead),
            readiness_score=42.0,
            why_this_now="The team needs a draft before filling audience fields.",
            merged_product_concept="A sparse rollout communications plan.",
            synthesis_rationale="Tests warning generation.",
            mvp_scope=["Fallback messaging"],
            first_milestones=["Identify the first audience owner"],
            validation_plan="Validate fallback messages with internal reviewers.",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
    return store, brief_id
