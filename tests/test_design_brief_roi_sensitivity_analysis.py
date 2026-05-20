from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_roi_sensitivity_analysis import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_roi_sensitivity_analysis,
    render_design_brief_roi_sensitivity_analysis,
    roi_sensitivity_analysis_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_roi_sensitivity_analysis_returns_stable_scenarios(tmp_path) -> None:
    store, brief_id = _store_with_roi_sensitivity_brief(tmp_path)
    try:
        report = build_design_brief_roi_sensitivity_analysis(store, brief_id)
        repeated = build_design_brief_roi_sensitivity_analysis(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert [scenario["id"] for scenario in report["scenario_assumptions"]] == [
        "best_case",
        "base_case",
        "worst_case",
    ]
    assert report["scenario_assumptions"][0]["payback_months"] < report["scenario_assumptions"][2]["payback_months"]
    assert {driver["id"] for driver in report["value_drivers"]} == {"V1", "V2", "V3"}
    assert {driver["id"] for driver in report["cost_drivers"]} == {"C1", "C2", "C3"}
    assert report["confidence_band"]["level"] in {"medium", "high"}
    assert not [gap for gap in report["evidence_gaps"] if gap["id"] in {"missing_buyer", "missing_workflow", "missing_validation"}]
    assert {item["id"] for item in report["evidence_references"]} >= {
        "design_brief.validation_plan",
        "bu-roi-sensitivity-lead.buyer",
        "bu-roi-sensitivity-lead.workflow_context",
    }


def test_roi_sensitivity_sparse_brief_reports_expected_evidence_gaps(tmp_path) -> None:
    store, brief_id = _store_with_roi_sensitivity_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_roi_sensitivity_analysis(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert [gap["id"] for gap in report["evidence_gaps"][:4]] == [
        "missing_pricing",
        "missing_buyer",
        "missing_workflow",
        "missing_validation",
    ]
    assert report["confidence_band"]["level"] == "low"
    assert any(risk["id"] == "B3" for risk in report["break_even_risks"])
    assert report["open_questions"][-1]["id"] == "Q3"


def test_roi_sensitivity_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_roi_sensitivity_analysis(store, "missing") is None
    finally:
        store.close()


def test_roi_sensitivity_renderers_and_filename(tmp_path) -> None:
    store, brief_id = _store_with_roi_sensitivity_brief(tmp_path)
    try:
        report = build_design_brief_roi_sensitivity_analysis(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_roi_sensitivity_analysis(report, "markdown")
    assert markdown.startswith("# ROI Sensitivity Analysis: ROI Sensitivity Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Scenario Assumptions" in markdown
    assert "## Break-Even Risks" in markdown
    assert json.loads(render_design_brief_roi_sensitivity_analysis(report, "json")) == report
    assert (
        roi_sensitivity_analysis_filename(report["design_brief"], "markdown")
        == f"{brief_id}-ROI-Sensitivity-Brief-roi-sensitivity-analysis.md"
    )
    assert roi_sensitivity_analysis_filename(report["design_brief"], "json").endswith(
        "-roi-sensitivity-analysis.json"
    )
    with pytest.raises(ValueError, match="Unsupported ROI sensitivity analysis format"):
        render_design_brief_roi_sensitivity_analysis(report, "xml")


def _store_with_roi_sensitivity_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"roi_sensitivity_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-roi-sensitivity-lead",
        title="ROI Sensitivity Lead",
        one_liner="Model renewal operations ROI.",
        category="application",
        problem="Customer success leaders cannot size expansion workflow payoff.",
        solution="Score renewal accounts and recommend next actions.",
        value_proposition="Reduce manual review and increase retained revenue.",
        specific_user="" if sparse else "revenue operations analyst",
        buyer="" if sparse else "VP of Customer Success",
        workflow_context="" if sparse else "renewal risk scoring workflow",
        current_workaround="manual spreadsheet review",
        validation_plan="" if sparse else "Compare pilot scores with renewal outcomes and sales manager feedback.",
        evidence_signals=[] if sparse else ["CRM renewal export", "manager interview notes"],
        domain_risks=[] if sparse else ["Revenue attribution may be noisy."],
        domain="revops",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse ROI Sensitivity Brief" if sparse else "ROI Sensitivity Brief",
            domain="revops",
            theme="renewal",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=22.0 if sparse else 78.0,
            why_this_now="" if sparse else "Renewal planning starts this quarter.",
            merged_product_concept="Renewal risk scoring and action planning.",
            synthesis_rationale="" if sparse else "Combines CRM evidence with workflow pain.",
            mvp_scope=[] if sparse else ["Renewal score", "Manager review queue"],
            first_milestones=["Define score inputs"],
            validation_plan="" if sparse else "Compare pilot scores with renewal outcomes and sales manager feedback.",
            risks=[] if sparse else ["Revenue attribution may be noisy."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
