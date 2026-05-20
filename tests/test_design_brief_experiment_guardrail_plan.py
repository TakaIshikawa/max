from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_experiment_guardrail_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_experiment_guardrail_plan,
    render_design_brief_experiment_guardrail_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_experiment_guardrail_plan_creates_success_and_guardrails(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_experiment_guardrail_plan(store, brief_id)
        repeated = build_design_brief_experiment_guardrail_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["strictness"] == "strict"
    assert report["summary"]["rollout_cap"] == "5% or 10 users, whichever is smaller"
    assert "claims intake review" in report["success_metrics"][0]["action"]
    assert "manual override" in report["guardrail_metrics"][1]["action"]
    assert report["stop_conditions"][0]["severity"] == "high"
    assert "Eligibility preview" in report["rollout_limits"][1]["action"]
    assert report["owner_actions"][1]["owner"] == "Engineering lead"


def test_low_risk_high_readiness_experiment_guardrail_is_standard(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, standard=True)
    try:
        report = build_design_brief_experiment_guardrail_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["strictness"] == "standard"
    assert report["summary"]["rollout_cap"] == "15% or 25 users, whichever is smaller"
    assert report["success_metrics"][0]["severity"] == "medium"


def test_sparse_experiment_guardrail_records_fallbacks_and_strictness(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_experiment_guardrail_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["strictness"] == "strict"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]


def test_experiment_guardrail_plan_missing_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_experiment_guardrail_plan(store, "missing") is None
    finally:
        store.close()


def test_render_experiment_guardrail_plan_formats(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_experiment_guardrail_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_experiment_guardrail_plan(report, "json")) == report
    markdown = render_design_brief_experiment_guardrail_plan(report, "markdown")
    assert markdown.startswith("# Experiment Guardrail Plan: Experiment Guardrail Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Stop Conditions" in markdown
    assert "## Rollout Limits" in markdown

    csv_text = render_design_brief_experiment_guardrail_plan(report, "csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0]["design_brief_id"] == brief_id
    assert {row["section"] for row in rows} == set(
        (
            "success_metrics",
            "guardrail_metrics",
            "stop_conditions",
            "rollout_limits",
            "review_checkpoints",
            "owner_actions",
        )
    )

    with pytest.raises(ValueError, match="Unsupported experiment guardrail plan format"):
        render_design_brief_experiment_guardrail_plan(report, "yaml")


def _store_with_brief(
    tmp_path, *, sparse: bool = False, standard: bool = False
) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"experiment_guardrail_{sparse}_{standard}.db"), wal_mode=True)
    lead = BuildableUnit(
        id=f"bu-experiment-guardrail-{sparse}-{standard}",
        title="Experiment Guardrail Lead",
        one_liner="Create experiment guardrails.",
        category="application",
        problem="Experiments launch without stop rules.",
        solution="Claims eligibility assistant",
        value_proposition="Reduce experiment risk.",
        specific_user="" if sparse else "claims operations lead",
        buyer="" if sparse else "claims director",
        workflow_context="" if sparse else "claims intake review",
        validation_plan="Run limited cohort experiment.",
        domain_risks=[] if sparse or standard else ["Wrong eligibility guidance requires manual override."],
        evidence_signals=["claims pilot request"],
        inspiring_insights=[],
        domain="insurance",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Experiment Guardrail Brief" if sparse else "Experiment Guardrail Brief",
            domain="insurance",
            theme="experiments",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=86.0 if standard else (45.0 if sparse else 74.0),
            why_this_now="Pilot is ready.",
            merged_product_concept="Claims eligibility assistant",
            synthesis_rationale="Guardrails bound experiment risk.",
            mvp_scope=[] if sparse else ["Eligibility preview", "Reviewer handoff"],
            first_milestones=["Define guardrails"],
            validation_plan="Run limited cohort experiment.",
            risks=[] if sparse or standard else ["Wrong eligibility guidance requires manual override."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
