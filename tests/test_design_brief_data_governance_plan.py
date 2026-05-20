from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_data_governance_plan import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_data_governance_plan,
    data_governance_plan_filename,
    render_design_brief_data_governance_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_data_governance_plan_returns_stable_json_serializable_output(tmp_path) -> None:
    store, brief_id = _store_with_governance_brief(tmp_path)
    try:
        report = build_design_brief_data_governance_plan(store, brief_id)
        repeated = build_design_brief_data_governance_plan(store, brief_id)
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
        "data_domains",
        "governance_controls",
        "evidence_references",
        "evidence_gaps",
        "open_questions",
        "source_ideas",
    ]
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["governance_posture"] == "privacy_review_required"
    assert report["summary"]["primary_data_owner"] == "Chief Compliance Officer"
    assert {domain["id"] for domain in report["data_domains"]} >= {"D1", "D2", "D3", "D4", "D5"}
    assert any(control["id"] == "G6" for control in report["governance_controls"])
    assert {item["id"] for item in report["evidence_references"]} >= {
        "design_brief.validation_plan",
        "bu-governance-lead.workflow_context",
        "bu-governance-lead.domain_risks",
    }
    assert report["evidence_gaps"] == []
    assert any("retention" in question["question"] for question in report["open_questions"])


def test_data_governance_plan_sparse_brief_reports_gaps(tmp_path) -> None:
    store, brief_id = _store_with_governance_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_data_governance_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["governance_posture"] == "governance_discovery_required"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]
    assert [gap["id"] for gap in report["evidence_gaps"]] == [
        "missing_buyer",
        "missing_workflow_context",
        "missing_mvp_scope",
    ]
    assert "smallest testable product behavior" in report["data_domains"][1]["evidence"]


def test_data_governance_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_data_governance_plan(store, "missing") is None
    finally:
        store.close()


def test_data_governance_plan_renderers_and_filename(tmp_path) -> None:
    store, brief_id = _store_with_governance_brief(tmp_path)
    try:
        report = build_design_brief_data_governance_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_data_governance_plan(report, "json")) == report
    markdown = render_design_brief_data_governance_plan(report, "markdown")
    assert markdown.startswith("# Data Governance Plan: Patient Data Governance Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Data Domains" in markdown
    assert "## Governance Controls" in markdown
    assert "## Evidence Gaps" in markdown

    assert (
        data_governance_plan_filename(report["design_brief"], "markdown")
        == f"{brief_id}-Patient-Data-Governance-Brief-data-governance-plan.md"
    )
    assert data_governance_plan_filename(report["design_brief"], "json").endswith(
        "-data-governance-plan.json"
    )
    with pytest.raises(ValueError, match="Unsupported data governance plan format"):
        render_design_brief_data_governance_plan(report, "yaml")


def _store_with_governance_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"governance_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-governance-lead",
        title="Governance Lead",
        one_liner="Govern patient handoff data.",
        category="application",
        problem="Care teams need controlled access to patient handoff notes.",
        solution="Govern workflow records, audit logs, and validation notes.",
        value_proposition="Reduce compliance review friction.",
        specific_user="" if sparse else "care coordinator",
        buyer="" if sparse else "Chief Compliance Officer",
        workflow_context="" if sparse else "patient discharge handoff workflow",
        validation_plan="" if sparse else "Pilot with synthetic patient records and audit review.",
        domain_risks=[] if sparse else ["HIPAA patient PII requires privacy and retention review."],
        evidence_signals=[] if sparse else ["privacy review notes", "EHR audit log export"],
        tech_approach="" if sparse else "Python API with EHR integration and masked logs.",
        domain="healthcare",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Governance Brief" if sparse else "Patient Data Governance Brief",
            domain="healthcare",
            theme="care-coordination",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=32.0 if sparse else 81.0,
            why_this_now="Compliance teams need a reviewable pilot path.",
            merged_product_concept="Coordinate patient discharge handoffs with governed records.",
            synthesis_rationale="Combines workflow automation with compliance evidence.",
            mvp_scope=[] if sparse else ["Handoff summary", "Audit log export"],
            first_milestones=[] if sparse else ["Map data inventory", "Approve retention defaults"],
            validation_plan="" if sparse else "Pilot with synthetic patient records and audit review.",
            risks=[] if sparse else ["HIPAA patient PII requires privacy and retention review."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
