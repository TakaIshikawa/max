from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_pricing_experiment_plan import (
    SCHEMA_VERSION,
    build_design_brief_pricing_experiment_plan,
    pricing_experiment_plan_filename,
    render_design_brief_pricing_experiment_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_pricing_experiment_plan_is_deterministic_and_json_serializable(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_pricing_experiment_plan(store, brief_id)
        repeated = build_design_brief_pricing_experiment_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert set(report) >= {
        "pricing_hypotheses",
        "value_metric_candidates",
        "target_segments",
        "experiment_stages",
        "guardrail_metrics",
        "decision_rules",
        "evidence_references",
        "evidence_gaps",
        "open_questions",
    }
    assert report["evidence_gaps"] == []
    assert any(metric["name"] == "connected integration" for metric in report["value_metric_candidates"])


def test_pricing_experiment_plan_sparse_brief_identifies_required_gaps(tmp_path) -> None:
    store, brief_id = _store(tmp_path, sparse=True)
    try:
        report = build_design_brief_pricing_experiment_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert [gap["id"] for gap in report["evidence_gaps"]] == [
        "missing_buyer",
        "missing_value_proposition",
        "missing_validation_plan",
        "missing_willingness_to_pay",
    ]


def test_pricing_experiment_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_pricing_experiment_plan(store, "missing") is None
    finally:
        store.close()


def test_pricing_experiment_plan_renderers_and_filename(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_pricing_experiment_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert json.loads(render_design_brief_pricing_experiment_plan(report, "json")) == report
    markdown = render_design_brief_pricing_experiment_plan(report)
    assert markdown.startswith("# Pricing Experiment Plan: Pricing Experiment Brief")
    assert "## Decision Rules" in markdown
    assert pricing_experiment_plan_filename(report["design_brief"]) == f"{brief_id}-Pricing-Experiment-Brief-pricing-experiment-plan.md"
    with pytest.raises(ValueError, match="Unsupported pricing experiment plan format"):
        render_design_brief_pricing_experiment_plan(report, "yaml")


def _store(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"pricing_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-pricing-lead",
        title="Pricing Lead",
        one_liner="Price integration workflow automation.",
        category="application",
        problem="API integration teams need a paid workflow tier.",
        solution="Package integration automation around connected APIs.",
        value_proposition="" if sparse else "Save implementation time with connected API automation.",
        specific_user="" if sparse else "integration lead",
        buyer="" if sparse else "Director of Partnerships",
        workflow_context="" if sparse else "partner API onboarding workflow",
        validation_plan="" if sparse else "Interview 5 buyers about budget and willingness to pay.",
        evidence_signals=[] if sparse else ["buyers asked for paid pilot", "budget owner confirmed"],
        domain_risks=[] if sparse else ["Price confusion could reduce activation."],
        domain="saas",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Pricing Brief" if sparse else "Pricing Experiment Brief",
            domain="saas",
            theme="pricing",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=21.0 if sparse else 79.0,
            why_this_now="Budget owners requested a paid pilot path." if not sparse else "",
            merged_product_concept="Partner API onboarding automation.",
            synthesis_rationale="Tests price against integration value.",
            mvp_scope=[] if sparse else ["Connect partner API", "Run first integration sync"],
            first_milestones=[] if sparse else ["Quote paid pilot", "Collect buyer feedback"],
            validation_plan="" if sparse else "Interview 5 buyers about budget and willingness to pay.",
            risks=[] if sparse else ["Price confusion could reduce activation."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
