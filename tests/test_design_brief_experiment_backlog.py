"""Tests for design brief experiment backlog generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.design_brief_experiment_backlog import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_experiment_backlog,
    experiment_backlog_filename,
    render_design_brief_experiment_backlog,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_experiment_backlog_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_experiment_backlog(store, brief_id)
        repeated = build_design_brief_experiment_backlog(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["title"] == "Experiment Backlog Brief"
    assert report["design_brief"]["source_idea_ids"] == [
        "bu-experiment-lead",
        "bu-experiment-support",
    ]
    assert report["summary"]["backlog_item_count"] == len(report["backlog_items"])
    assert report["summary"]["backlog_item_count"] >= 1
    assert report["summary"]["evidence_reference_count"] >= 1
    assert report["recommended_next_actions"]
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_priority_scores_are_deterministic_and_rank_urgent_gaps(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_experiment_backlog(store, brief_id)
    finally:
        store.close()

    assert report is not None
    items = report["backlog_items"]
    scores = [item["priority_score"] for item in items]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= score <= 100 for score in scores)
    assert all(
        {"evidence_gap", "risk", "readiness", "validation_urgency", "effort_penalty", "total"}
        <= set(item["priority_breakdown"])
        for item in items
    )
    top = items[0]
    assert top["priority_breakdown"]["evidence_gap"] > 0
    assert top["priority_breakdown"]["readiness"] > 0
    assert top["priority_breakdown"]["validation_urgency"] > 0
    assert report["summary"]["fallbacks_used"] == ["specific_user", "buyer", "workflow_context"]
    assert report["evidence_gaps"]


def test_markdown_rendering_includes_experiment_details_and_source_references(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_experiment_backlog(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_experiment_backlog(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_experiment_backlog(report, fmt="markdown")
    assert markdown.startswith("# Experiment Backlog: Experiment Backlog Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Design Brief Summary" in markdown
    assert "## Prioritized Experiments" in markdown
    assert "Hypothesis:" in markdown
    assert "Success metric:" in markdown
    assert "Source idea references: bu-experiment-lead" in markdown
    assert "## Recommended Next Actions" in markdown


def test_csv_rendering_includes_stable_experiment_rows(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_experiment_backlog(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_experiment_backlog(report, fmt="csv")
    repeated = render_design_brief_experiment_backlog(report, fmt="csv")
    reader = csv.DictReader(StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert len(rows) == len(report["backlog_items"])

    first_item = report["backlog_items"][0]
    first_row = rows[0]
    assert first_row["design_brief_id"] == brief_id
    assert first_row["design_brief_title"] == "Experiment Backlog Brief"
    assert first_row["experiment_id"] == first_item["id"]
    assert first_row["experiment_title"] == first_item["title"]
    assert first_row["rank"] == str(first_item["rank"])
    assert first_row["priority"] == str(first_item["priority_score"])
    assert first_row["hypothesis"] == first_item["hypothesis"]
    assert first_row["owner_or_persona"] == first_item["target_persona"]
    assert first_row["method"] == first_item["experiment_type"]
    assert first_row["success_metric"] == first_item["success_metric"]
    assert first_row["evidence_inputs"] == "; ".join(first_item["required_evidence"])
    assert first_row["effort"] == first_item["effort"]
    assert first_row["risk"] == first_item["risk_reduction"]
    assert first_row["next_action"] == "; ".join(first_item["recommended_next_actions"])


def test_csv_rendering_handles_sparse_and_empty_reports(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_experiment_backlog(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rows = list(
        csv.DictReader(StringIO(render_design_brief_experiment_backlog(report, fmt="csv")))
    )
    assert rows
    assert all(row["experiment_id"] for row in rows)
    assert all(row["hypothesis"] for row in rows)
    assert all(row["method"] for row in rows)
    assert all(row["next_action"] for row in rows)

    header_only = render_design_brief_experiment_backlog({"backlog_items": []}, fmt="csv")
    assert header_only == ",".join(CSV_COLUMNS) + "\n"
    assert list(csv.DictReader(StringIO(header_only))) == []


def test_csv_rendering_orders_rows_by_rank_then_id() -> None:
    report = {
        "design_brief": {"id": "dbf-order", "title": "Ordering"},
        "backlog_items": [
            {
                "id": "EXP2",
                "rank": 2,
                "title": "Second",
                "hypothesis": "Second hypothesis",
                "experiment_type": "prototype test",
                "target_persona": "designer",
                "success_metric": "Second metric",
                "required_evidence": ["second evidence"],
                "source_idea_ids": ["bu-2"],
                "source_fields": ["mvp_scope"],
                "effort": "medium",
                "risk_reduction": "medium",
                "priority_score": 50,
                "recommended_next_actions": ["Run second."],
            },
            {
                "id": "EXP1",
                "rank": 1,
                "title": "First",
                "hypothesis": "First hypothesis",
                "experiment_type": "interview",
                "target_persona": "buyer",
                "success_metric": "First metric",
                "required_evidence": ["first evidence"],
                "source_idea_ids": ["bu-1"],
                "source_fields": ["buyer"],
                "effort": "low",
                "risk_reduction": "high",
                "priority_score": 70,
                "recommended_next_actions": ["Run first."],
            },
        ],
    }

    rows = list(
        csv.DictReader(StringIO(render_design_brief_experiment_backlog(report, fmt="csv")))
    )

    assert [row["experiment_id"] for row in rows] == ["EXP1", "EXP2"]
    assert [row["experiment_title"] for row in rows] == ["First", "Second"]


def test_sparse_brief_returns_actionable_fallback_experiments(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_experiment_backlog(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert len(report["backlog_items"]) >= 3
    assert any(item["experiment_type"] == "evidence audit" for item in report["backlog_items"])
    assert all(item["hypothesis"] for item in report["backlog_items"])
    assert all(item["required_evidence"] for item in report["backlog_items"])
    assert all(item["success_metric"] for item in report["backlog_items"])
    assert all(item["recommended_next_actions"] for item in report["backlog_items"])


def test_experiment_backlog_missing_brief_invalid_format_and_filename(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_experiment_backlog.db"), wal_mode=True)
    try:
        assert build_design_brief_experiment_backlog(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported experiment backlog format: yaml"):
        render_design_brief_experiment_backlog({"design_brief": {}}, fmt="yaml")

    design_brief = {"id": "dbf-123", "title": "Experiment Backlog: Alpha / Beta"}
    assert (
        experiment_backlog_filename(design_brief)
        == "dbf-123-Experiment-Backlog-Alpha-Beta-experiment-backlog.md"
    )
    assert (
        experiment_backlog_filename(design_brief, fmt="json")
        == "dbf-123-Experiment-Backlog-Alpha-Beta-experiment-backlog.json"
    )
    assert (
        experiment_backlog_filename(design_brief, fmt="csv")
        == "dbf-123-Experiment-Backlog-Alpha-Beta-experiment-backlog.csv"
    )


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_experiment_backlog.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-experiment-lead",
        title="Experiment Lead",
        one_liner="Prioritize validation experiments for autonomous agents.",
        category="application",
        problem="Agents need ranked validation work before implementation commitment.",
        solution="Generate deterministic experiment backlogs from design briefs.",
        value_proposition="Reduce premature build work with evidence-backed validation.",
        specific_user="product engineer",
        buyer="engineering director",
        workflow_context="pre-build design validation",
        current_workaround="manual validation checklist",
        why_now="Design briefs already persist validation inputs.",
        validation_plan="Run a prototype test with platform teams and compare pass/fail evidence.",
        first_10_customers="developer platform teams",
        domain_risks=["Security review may block autonomous execution."],
        evidence_signals=["sig-experiment-1"],
        inspiring_insights=["ins-experiment-1"],
        tech_approach="Python deterministic scoring over persisted brief fields.",
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-experiment-support",
        title="Experiment Support",
        one_liner="Trace validation work back to source ideas.",
        category="application",
        problem="Validation tasks lose their idea lineage.",
        solution="Attach source references to every experiment.",
        value_proposition="Make evidence collection auditable.",
        specific_user="research lead",
        buyer="product director",
        workflow_context="validation planning",
        domain_risks=["Adoption signal may be too weak for prioritization."],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Experiment Backlog Brief",
            domain="developer-tools",
            theme="experiment-backlog",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=82.0,
            why_this_now="Agents need validation work queued before build commitment.",
            merged_product_concept="A deterministic experiment backlog for persisted design briefs.",
            synthesis_rationale="Extends design briefs with ranked validation tasks.",
            mvp_scope=["Backlog JSON artifact", "Markdown backlog export"],
            first_milestones=["Generate ranked experiments"],
            validation_plan="Run a prototype test with platform teams and compare pass/fail evidence.",
            risks=["Security review may block autonomous execution."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / "design_brief_sparse_experiment_backlog.db"), wal_mode=True
    )
    lead = BuildableUnit(
        id="bu-experiment-sparse",
        title="Sparse Experiment Lead",
        one_liner="Create validation work with weak inputs.",
        category="application",
        problem="Experiment input is incomplete.",
        solution="Use fallback validation experiments.",
        value_proposition="Keep validation moving while gaps are visible.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Experiment Brief",
            domain="developer-tools",
            theme="experiment-backlog",
            lead=Candidate(unit=lead),
            readiness_score=35.0,
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
