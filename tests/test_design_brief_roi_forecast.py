"""Tests for design brief ROI forecast generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_roi_forecast import (
    SCHEMA_VERSION,
    build_design_brief_roi_forecast,
    render_design_brief_roi_forecast,
    roi_forecast_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_roi_forecast_returns_stable_json_serializable_report(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_roi_forecast(store, brief_id)
        repeated = build_design_brief_roi_forecast(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.roi_forecast"
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["buyer"] == "VP of Customer Operations"
    assert report["design_brief"]["source_idea_ids"] == ["bu-roi-lead", "bu-roi-support"]
    assert report["summary"]["implementation_cost_low_usd"] > 0
    assert report["summary"]["annual_benefit_low_usd"] > 0
    assert report["summary"]["payback_expected_months"] > 0
    assert report["confidence_level"]["level"] in {"medium", "high"}
    assert {item["id"] for item in report["evidence_references"]} >= {
        "design_brief.validation_plan",
        "bu-roi-lead.evidence_rationale",
        "sig-roi-workflow",
        "ins-roi-ops",
    }
    assert any(
        item["id"] == "adoption_or_revenue_gain"
        for item in report["benefit_bands"]["components"]
    )
    assert json.loads(json.dumps(report))["kind"] == "max.design_brief.roi_forecast"


def test_build_design_brief_roi_forecast_thin_evidence_adds_conservative_fallback(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_roi_forecast(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["confidence_level"]["level"] == "low"
    assert any("conservative adoption" in item["assumption"] for item in report["assumptions"])
    assert any(
        item["id"] == "thin_evidence_discount"
        for item in report["benefit_bands"]["components"]
    )
    assert report["next_actions"][0] == (
        "Define the validation plan and success threshold that will confirm payback assumptions."
    )
    assert any(
        "Collect at least three independent evidence" in item for item in report["next_actions"]
    )


def test_render_design_brief_roi_forecast_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_roi_forecast(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_roi_forecast(report, fmt="markdown")
    assert markdown.startswith("# ROI Forecast: ROI Forecast Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Assumptions" in markdown
    assert "## Payback Range" in markdown
    assert "## Confidence" in markdown
    assert "## Next Actions" in markdown
    assert "Implementation cost:" in markdown
    assert "Confidence:" in markdown

    rendered_json = render_design_brief_roi_forecast(report, fmt="json")
    assert json.loads(rendered_json) == report

    with pytest.raises(ValueError, match="Unsupported ROI forecast format: yaml"):
        render_design_brief_roi_forecast(report, fmt="yaml")


def test_roi_forecast_filename_sanitizes_brief_id_and_title() -> None:
    brief = {"id": "dbf/roi 001", "title": "ROI Forecast: API Brief!"}

    assert (
        roi_forecast_filename(brief, fmt="markdown")
        == "dbf-roi-001-ROI-Forecast-API-Brief-roi-forecast.md"
    )
    assert (
        roi_forecast_filename(brief, fmt="json")
        == "dbf-roi-001-ROI-Forecast-API-Brief-roi-forecast.json"
    )


def test_build_design_brief_roi_forecast_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_roi_forecast.db"), wal_mode=True)
    try:
        report = build_design_brief_roi_forecast(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"design_brief_roi_forecast_{sparse}.db"), wal_mode=True)
    if sparse:
        lead = BuildableUnit(
            id="bu-roi-sparse-lead",
            title="Sparse ROI Lead",
            one_liner="Forecast ROI with minimal inputs.",
            category="application",
            problem="Prioritization needs a rough financial frame.",
            solution="Create a deterministic ROI forecast.",
            value_proposition="",
            specific_user="",
            buyer="",
            workflow_context="",
            current_workaround="",
            validation_plan="",
            first_10_customers="",
            domain_risks=[],
            evidence_rationale="",
            evidence_signals=[],
            inspiring_insights=[],
            tech_approach="",
            suggested_stack={},
            domain="operations",
            status="approved",
        )
        supporting: list[Candidate] = []
        readiness_score = 22.0
        validation_plan = ""
        risks: list[str] = []
    else:
        lead = BuildableUnit(
            id="bu-roi-lead",
            title="ROI Workflow Lead",
            one_liner="Forecast ROI for approved operations briefs.",
            category="application",
            problem="Customer operations teams cannot compare approved briefs by payback.",
            solution="Export deterministic ROI forecasts with cost and benefit bands.",
            value_proposition="Reduce manual prioritization time and surface payback tradeoffs.",
            specific_user="customer operations manager",
            buyer="VP of Customer Operations",
            workflow_context="customer onboarding audit handoff workflow",
            current_workaround="manual spreadsheet prioritization and stakeholder review",
            why_now="Operations leaders are reviewing approved briefs for quarterly planning.",
            validation_plan="Pilot with three operations managers and compare planning cycle time.",
            first_10_customers="10 regulated customer success teams",
            domain_risks=["Audit evidence may be required before launch."],
            evidence_rationale="Customer interviews show manual audit handoffs delay planning.",
            evidence_signals=["sig-roi-workflow", "sig-roi-budget"],
            inspiring_insights=["ins-roi-ops"],
            tech_approach="FastAPI export backed by persisted design brief data.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            composability_notes="Connect forecast outputs to stakeholder review packets.",
            domain="operations",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-roi-support",
            title="ROI Support Evidence",
            one_liner="Capture adoption evidence for ROI forecasts.",
            category="automation",
            problem="Stakeholders need consistent benefit assumptions.",
            solution="Attach adoption evidence to forecast reports.",
            value_proposition="Improve confidence in prioritization decisions.",
            specific_user="program manager",
            buyer="VP of Customer Operations",
            workflow_context="quarterly planning workflow",
            current_workaround="ad hoc notes",
            validation_plan="Review forecast assumptions with budget owners.",
            first_10_customers="regulated operations teams",
            domain_risks=["Budget owner may reject unvalidated revenue assumptions."],
            evidence_rationale=(
                "Budget owners asked for payback ranges before approving build work."
            ),
            evidence_signals=["sig-roi-budget-owner"],
            tech_approach="Render JSON and Markdown ROI artifacts.",
            suggested_stack={"artifact": "markdown"},
            domain="operations",
            status="approved",
        )
        supporting = [Candidate(unit=support)]
        readiness_score = 86.0
        validation_plan = "Confirm cycle-time savings and budget owner acceptance with pilot teams."
        risks = ["Revenue impact needs validation before executive review."]

    store.insert_buildable_unit(lead)
    for candidate in supporting:
        store.insert_buildable_unit(candidate.unit)

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="ROI Forecast Brief",
            domain="operations",
            theme="planning-prioritization",
            lead=Candidate(unit=lead),
            supporting=supporting,
            readiness_score=readiness_score,
            why_this_now="Approved design briefs need prioritization for execution planning.",
            merged_product_concept=(
                "A deterministic ROI forecast artifact for persisted design briefs."
            ),
            synthesis_rationale=(
                "" if sparse else "Combines source evidence into cost, benefit, and payback ranges."
            ),
            mvp_scope=["ROI JSON", "ROI Markdown"] if not sparse else ["ROI JSON"],
            first_milestones=["Return ROI JSON", "Render Markdown forecast"] if not sparse else [],
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id, *[candidate.unit.id for candidate in supporting]],
            design_status="approved",
        )
    )
    return store, brief_id
