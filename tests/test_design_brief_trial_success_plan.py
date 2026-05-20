from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_trial_success_plan import (
    SCHEMA_VERSION,
    build_design_brief_trial_success_plan,
    render_design_brief_trial_success_plan,
    trial_success_plan_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_trial_success_plan_is_deterministic_and_complete(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_trial_success_plan(store, brief_id)
        repeated = build_design_brief_trial_success_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert set(report) >= {
        "trial_objectives",
        "activation_milestones",
        "success_metrics",
        "disqualification_signals",
        "stakeholder_checkpoints",
        "evidence_references",
        "evidence_gaps",
        "open_questions",
    }
    assert report["evidence_gaps"] == []
    assert report["summary"]["trial_posture"] == "ready_for_trial_design"


def test_trial_success_plan_sparse_brief_surfaces_required_gaps(tmp_path) -> None:
    store, brief_id = _store(tmp_path, sparse=True)
    try:
        report = build_design_brief_trial_success_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert [gap["id"] for gap in report["evidence_gaps"]] == [
        "missing_validation_plan",
        "missing_target_user",
        "missing_measurable_outcome",
    ]
    assert any("Target trial user is missing" in item["question"] for item in report["open_questions"])


def test_trial_success_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_trial_success_plan(store, "missing") is None
    finally:
        store.close()


def test_trial_success_plan_renderers_and_filename(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_trial_success_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert json.loads(render_design_brief_trial_success_plan(report, "json")) == report
    markdown = render_design_brief_trial_success_plan(report)
    assert markdown.startswith("# Trial Success Plan: Trial Success Brief")
    assert "## Activation Milestones" in markdown
    assert trial_success_plan_filename(report["design_brief"]) == f"{brief_id}-Trial-Success-Brief-trial-success-plan.md"
    with pytest.raises(ValueError, match="Unsupported trial success plan format"):
        render_design_brief_trial_success_plan(report, "yaml")


def _store(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"trial_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-trial-lead",
        title="Trial Lead",
        one_liner="Trial onboarding automation.",
        category="application",
        problem="Teams need a measurable pilot path.",
        solution="Guide trial activation and outcome review.",
        value_proposition="Reduce trial ambiguity.",
        specific_user="" if sparse else "implementation manager",
        buyer="" if sparse else "Head of Customer Success",
        workflow_context="" if sparse else "customer onboarding trial workflow",
        validation_plan="" if sparse else "Measure 80% activation within two weeks.",
        evidence_signals=[] if sparse else ["3 pilot teams requested activation reporting"],
        domain_risks=[] if sparse else ["Manual rescue could hide activation failure."],
        domain="saas",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Trial Brief" if sparse else "Trial Success Brief",
            domain="saas",
            theme="trial",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=20.0 if sparse else 84.0,
            why_this_now="Trials need measurable conversion evidence.",
            merged_product_concept="Activation workflow for onboarding trials.",
            synthesis_rationale="Combines onboarding automation and success review.",
            mvp_scope=[] if sparse else ["Invite pilot account", "Complete first onboarding task"],
            first_milestones=[] if sparse else ["Pilot account invited", "First task completed"],
            validation_plan="" if sparse else "Measure 80% activation within two weeks.",
            risks=[] if sparse else ["Manual rescue could hide activation failure."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
