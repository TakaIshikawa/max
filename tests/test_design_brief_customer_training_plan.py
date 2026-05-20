from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_customer_training_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_customer_training_plan,
    render_design_brief_customer_training_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_customer_training_plan_uses_brief_context(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_training_plan(store, brief_id)
        repeated = build_design_brief_customer_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["target_user"] == "support operations manager"
    assert report["summary"]["workflow_context"] == "weekly support escalation review"
    assert report["summary"]["fallbacks_used"] == []
    assert "Escalation automation" in report["training_modules"][0]["action"]
    assert "Triage dashboard" in report["training_modules"][1]["action"]
    assert "privacy approval" in report["practice_exercises"][1]["action"]
    assert report["completion_signals"][0]["evidence"].startswith("80%")


def test_sparse_customer_training_plan_records_fallbacks(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_customer_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]
    assert report["learner_segments"][0]["action"] == (
        "Train Sparse Customer Training users to complete Sparse Customer Training operating workflow."
    )
    assert report["training_modules"][1]["action"].endswith(
        "smallest testable product behavior."
    )


def test_build_design_brief_customer_training_plan_missing_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_customer_training_plan(store, "missing") is None
    finally:
        store.close()


def test_render_design_brief_customer_training_plan_formats(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_customer_training_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_customer_training_plan(report, "json")) == report
    markdown = render_design_brief_customer_training_plan(report, "markdown")
    assert markdown.startswith("# Customer Training Plan: Customer Training Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Training Modules" in markdown
    assert "## Practice Exercises" in markdown

    csv_text = render_design_brief_customer_training_plan(report, "csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert {row["section"] for row in rows} == set(
        (
            "learner_segments",
            "training_modules",
            "prerequisite_setup",
            "practice_exercises",
            "completion_signals",
            "post_training_followups",
        )
    )
    assert rows[0]["design_brief_id"] == brief_id

    with pytest.raises(ValueError, match="Unsupported customer training plan format"):
        render_design_brief_customer_training_plan(report, "yaml")


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"customer_training_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id=f"bu-customer-training-{sparse}",
        title="Customer Training Lead",
        one_liner="Build customer training artifacts.",
        category="application",
        problem="Customers need repeatable enablement.",
        solution="Escalation automation training export.",
        value_proposition="Make onboarding safer.",
        specific_user="" if sparse else "support operations manager",
        buyer="" if sparse else "support director",
        workflow_context="" if sparse else "weekly support escalation review",
        validation_plan="Run training with customer admins.",
        domain_risks=[] if sparse else ["Requires privacy approval for ticket examples."],
        evidence_signals=["two customer interviews"],
        inspiring_insights=["admins want scenario practice"],
        domain="support",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Customer Training Brief" if sparse else "Customer Training Brief",
            domain="support",
            theme="training",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=48.0 if sparse else 82.0,
            why_this_now="Support teams are expanding.",
            merged_product_concept="Escalation automation" if not sparse else "",
            synthesis_rationale="Training connects workflow and support risks.",
            mvp_scope=[] if sparse else ["Triage dashboard", "Escalation handoff"],
            first_milestones=["Export JSON", "Export Markdown"],
            validation_plan="Observe trained admins completing exercises.",
            risks=[] if sparse else ["Requires privacy approval for ticket examples."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
