from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_telemetry_quality_plan import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_telemetry_quality_plan,
    render_design_brief_telemetry_quality_plan,
    telemetry_quality_plan_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_telemetry_quality_plan_returns_stable_json_serializable_output(tmp_path) -> None:
    store, brief_id = _store_with_telemetry_brief(tmp_path)
    try:
        report = build_design_brief_telemetry_quality_plan(store, brief_id)
        repeated = build_design_brief_telemetry_quality_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert list(report) == [
        "schema_version",
        "kind",
        "source",
        "design_brief",
        "summary",
        "telemetry_events",
        "quality_risks",
        "instrumentation_gaps",
        "acceptance_checks",
        "evidence_references",
        "source_ideas",
    ]
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["quality_posture"] == "quality_risk_review_required"
    assert {event["category"] for event in report["telemetry_events"]} >= {
        "activation",
        "value",
        "validation",
        "guardrail",
        "data_quality",
    }
    assert any(risk["id"] == "Q3" for risk in report["quality_risks"])
    assert report["instrumentation_gaps"] == []
    assert {item["id"] for item in report["evidence_references"]} >= {
        "design_brief.validation_plan",
        "bu-telemetry-lead.workflow_context",
    }


def test_telemetry_quality_plan_sparse_brief_reports_unknowns_and_open_questions(tmp_path) -> None:
    store, brief_id = _store_with_telemetry_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_telemetry_quality_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["quality_posture"] == "instrumentation_discovery_required"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]
    assert [gap["id"] for gap in report["instrumentation_gaps"]] == [
        "missing_workflow_context",
        "missing_mvp_scope",
        "missing_success_metric",
        "missing_evidence",
        "missing_guardrail_thresholds",
    ]
    assert "unknown validation evidence" in report["telemetry_events"][2]["evidence"]
    assert "unknown risk threshold" in report["telemetry_events"][3]["evidence"]


def test_telemetry_quality_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_telemetry_quality_plan(store, "missing") is None
    finally:
        store.close()


def test_telemetry_quality_plan_renderers_and_filename(tmp_path) -> None:
    store, brief_id = _store_with_telemetry_brief(tmp_path)
    try:
        report = build_design_brief_telemetry_quality_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_telemetry_quality_plan(report, "json")) == report
    markdown = render_design_brief_telemetry_quality_plan(report, "markdown")
    assert markdown.startswith("# Telemetry Quality Plan: Telemetry Quality Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Telemetry Events" in markdown
    assert "## Quality Risks" in markdown
    assert "## Instrumentation Gaps" in markdown
    assert (
        telemetry_quality_plan_filename(report["design_brief"], "markdown")
        == f"{brief_id}-Telemetry-Quality-Brief-telemetry-quality-plan.md"
    )
    assert telemetry_quality_plan_filename(report["design_brief"], "json").endswith(
        "-telemetry-quality-plan.json"
    )
    with pytest.raises(ValueError, match="Unsupported telemetry quality plan format"):
        render_design_brief_telemetry_quality_plan(report, "yaml")


def _store_with_telemetry_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"telemetry_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-telemetry-lead",
        title="Telemetry Lead",
        one_liner="Measure API workflow quality.",
        category="application",
        problem="Operations teams cannot trust integration metrics.",
        solution="Instrument API syncs, activation, validation decisions, and quality alerts.",
        value_proposition="Improve metric confidence for launch decisions.",
        specific_user="" if sparse else "operations analyst",
        buyer="" if sparse else "VP Operations",
        workflow_context="" if sparse else "partner API onboarding workflow",
        validation_plan="" if sparse else "Replay pilot API syncs and reconcile metrics against source records.",
        domain_risks=[] if sparse else ["Integration payload drift can break telemetry quality."],
        evidence_signals=[] if sparse else ["API sync audit", "metric reconciliation sample"],
        tech_approach="" if sparse else "Python API events with warehouse validation checks.",
        domain="data-platform",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Telemetry Brief" if sparse else "Telemetry Quality Brief",
            domain="data-platform",
            theme="telemetry",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=25.0 if sparse else 78.0,
            why_this_now="Launch decisions need trusted telemetry.",
            merged_product_concept="Measure partner API onboarding with validation-ready events.",
            synthesis_rationale="Connects integration telemetry to launch metrics.",
            mvp_scope=[] if sparse else ["API account connected", "First sync completed"],
            first_milestones=[] if sparse else ["Define event schema", "Reconcile warehouse metrics"],
            validation_plan="" if sparse else "Replay pilot API syncs and reconcile metrics against source records.",
            risks=[] if sparse else ["Integration payload drift can break telemetry quality."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
