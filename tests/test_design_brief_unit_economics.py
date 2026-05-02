"""Tests for design brief unit economics generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.design_brief_unit_economics import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_unit_economics,
    render_design_brief_unit_economics,
    unit_economics_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def test_build_design_brief_unit_economics_is_deterministic_and_traceable(tmp_path) -> None:
    store, brief_id = _store_with_unit_economics_brief(tmp_path)
    try:
        report = build_design_brief_unit_economics(store, brief_id)
        repeated = build_design_brief_unit_economics(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.unit_economics"
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["buyer"] == "VP of Customer Operations"
    assert report["design_brief"]["workflow_context"] == "regulated onboarding review"
    assert report["design_brief"]["source_idea_ids"] == [
        "bu-unit-econ-lead",
        "bu-unit-econ-support",
    ]
    assert report["revenue_model"]["source_idea_ids"] == [
        "bu-unit-econ-lead",
        "bu-unit-econ-support",
    ]
    assert report["revenue_model"]["buyer_budget_owner"] == "VP of Customer Operations"
    assert (
        "successful regulated onboarding review outcomes"
        in report["revenue_model"]["pricing_basis"]
    )
    assert report["revenue_model"]["target_monthly_price_band_usd"]["low"] > 0
    assert [channel["id"] for channel in report["acquisition_channels"]] == [
        "channel_design_partner_outreach",
        "channel_validation_interviews",
        "channel_evidence_followups",
    ]
    assert {item["id"] for item in report["cost_drivers"]} == {
        "cost_driver_delivery",
        "cost_driver_runtime",
        "cost_driver_validation",
    }
    assert report["payback_bands"]["expected_months"] > 0
    assert report["gross_margin_risk_notes"]
    assert [case["case"] for case in report["sensitivity_cases"]] == [
        "conservative",
        "base",
        "upside",
    ]
    assert report["validation_questions"]
    assert json.loads(json.dumps(report))["kind"] == "max.design_brief.unit_economics"


def test_build_design_brief_unit_economics_missing_optional_fields_uses_fallbacks(
    tmp_path,
) -> None:
    store, brief_id = _store_with_unit_economics_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_unit_economics(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["confidence"]["level"] == "low"
    assert report["design_brief"]["buyer"] == "target buyer"
    assert report["design_brief"]["workflow_context"] == "target workflow"
    assert report["revenue_model"]["packaging"] == "concierge pilot before recurring pricing"
    assert report["revenue_model"]["initial_customer_segment"] == "first 10 design partners"
    assert [channel["id"] for channel in report["acquisition_channels"]] == [
        "channel_design_partner_outreach",
        "channel_validation_interviews",
        "channel_manual_research",
    ]
    assert any(
        note["id"] == "margin_risk_missing_evidence" for note in report["gross_margin_risk_notes"]
    )
    assert any(risk["id"] == "risk_missing_market_evidence" for risk in report["risks"])
    assert (
        report["sensitivity_cases"][0]["payback_months"]
        > report["sensitivity_cases"][1]["payback_months"]
    )


def test_render_design_brief_unit_economics_json_markdown_and_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_unit_economics_brief(tmp_path)
    try:
        report = build_design_brief_unit_economics(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_unit_economics(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_unit_economics(report, fmt="markdown")
    repeated_markdown = render_design_brief_unit_economics(report, fmt="markdown")
    assert markdown == repeated_markdown
    assert markdown.startswith("# Unit Economics: Unit Economics Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Revenue Model" in markdown
    assert "## Acquisition Channels" in markdown
    assert "## Cost Drivers" in markdown
    assert "## Payback Bands" in markdown
    assert "## Gross Margin Risks" in markdown
    assert "## Sensitivity Cases" in markdown
    assert "## Validation Questions" in markdown
    assert "bu-unit-econ-lead" in markdown

    csv_text = render_design_brief_unit_economics(report, fmt="csv")
    repeated_csv = render_design_brief_unit_economics(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))
    rows_by_id = {row["row_id"]: row for row in rows}

    assert csv_text == repeated_csv
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert {row["section"] for row in rows} == {
        "acquisition_costs",
        "revenue_assumptions",
        "margin_drivers",
        "payback_notes",
        "sensitivity_rows",
    }
    assert rows_by_id["revenue_target_monthly_price_band_usd"]["low_usd"] == str(
        report["revenue_model"]["target_monthly_price_band_usd"]["low"]
    )
    assert rows_by_id["revenue_target_monthly_price_band_usd"]["high_usd"] == str(
        report["revenue_model"]["target_monthly_price_band_usd"]["high"]
    )
    assert rows_by_id["assumption_margin"]["label"] == "Gross margin target"
    assert rows_by_id["assumption_margin"]["basis"]
    assert (
        rows_by_id["channel_design_partner_outreach"]["note"]
        == report["acquisition_channels"][0]["rationale"]
    )
    assert rows_by_id["payback_expected_months"]["months"] == str(
        report["payback_bands"]["expected_months"]
    )
    assert rows_by_id["sensitivity_conservative"]["note"] == report["sensitivity_cases"][0][
        "assumption_shift"
    ]
    assert rows_by_id["revenue_source_idea_ids"]["source_idea_ids"] == (
        "bu-unit-econ-lead;bu-unit-econ-support"
    )

    with pytest.raises(ValueError, match="Unsupported unit economics format: yaml"):
        render_design_brief_unit_economics(report, fmt="yaml")


def test_unit_economics_filename_sanitizes_brief_id_and_title() -> None:
    brief = {"id": "dbf/unit econ 001", "title": "Unit Economics: API Brief!"}

    assert (
        unit_economics_filename(brief, fmt="markdown")
        == "dbf-unit-econ-001-Unit-Economics-API-Brief-unit-economics.md"
    )
    assert (
        unit_economics_filename(brief, fmt="json")
        == "dbf-unit-econ-001-Unit-Economics-API-Brief-unit-economics.json"
    )
    assert (
        unit_economics_filename(brief, fmt="csv")
        == "dbf-unit-econ-001-Unit-Economics-API-Brief-unit-economics.csv"
    )


def test_build_design_brief_unit_economics_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_unit_economics.db"), wal_mode=True)
    try:
        assert build_design_brief_unit_economics(store, "dbf-missing") is None
    finally:
        store.close()


def _store_with_unit_economics_brief(
    tmp_path,
    *,
    sparse: bool = False,
) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_unit_economics_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-unit-econ-sparse",
            title="Sparse Unit Economics Lead",
            one_liner="Create unit economics with minimal inputs.",
            category="application",
            problem="Teams need a conservative economics frame.",
            solution="Generate fallback assumptions.",
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
            tech_approach="",
            suggested_stack={},
            domain="operations",
            status="approved",
        )
        supporting: list[Candidate] = []
        readiness_score = 20.0
        validation_plan = ""
        mvp_scope = ["Economics JSON"]
        risks: list[str] = []
        evaluations = False
    else:
        lead = BuildableUnit(
            id="bu-unit-econ-lead",
            title="Unit Economics Lead",
            one_liner="Generate unit economics for design briefs.",
            category="application",
            problem="Portfolio teams cannot see payback and gross margin risks.",
            solution="Render deterministic economics from persisted briefs.",
            value_proposition="Reduce approval friction with pricing and cost-to-serve assumptions.",
            specific_user="portfolio operations lead",
            buyer="VP of Customer Operations",
            workflow_context="regulated onboarding review",
            current_workaround="manual spreadsheet economics model",
            why_now="Approved briefs need investment review before build planning.",
            validation_plan="Review willingness to pay with five budget owners.",
            first_10_customers="10 regulated customer operations teams",
            domain_risks=["Usage-sensitive model costs could compress margins."],
            evidence_rationale="Budget owners asked for payback before approving pilots.",
            evidence_signals=["sig-unit-econ-workflow"],
            tech_approach="FastAPI artifact generation with Markdown and JSON renderers.",
            suggested_stack={"language": "python", "model": "llm"},
            domain="operations",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-unit-econ-support",
            title="Unit Economics Support",
            one_liner="Support source idea for economics assumptions.",
            category="automation",
            problem="Support effort is unknown before pilots.",
            solution="Track implementation and success costs.",
            value_proposition="Make cost-to-serve visible before launch.",
            specific_user="customer success lead",
            buyer="VP of Customer Operations",
            workflow_context="pilot onboarding",
            current_workaround="ad hoc customer notes",
            validation_plan="Measure support effort during paid pilots.",
            first_10_customers="regulated operations teams",
            domain_risks=["Custom integrations may slow payback."],
            evidence_signals=["sig-unit-econ-support"],
            tech_approach="Structured economics report.",
            suggested_stack={"artifact": "markdown"},
            domain="operations",
            status="approved",
        )
        supporting = [Candidate(unit=support)]
        readiness_score = 86.0
        validation_plan = "Confirm price, payback, and support effort with pilot buyers."
        mvp_scope = ["Unit economics JSON", "Unit economics Markdown"]
        risks = ["Payback assumptions need buyer validation."]
        evaluations = True

    store.insert_buildable_unit(lead)
    for candidate in supporting:
        store.insert_buildable_unit(candidate.unit)

    if evaluations:
        store.insert_evaluation(_evaluation(lead.id))

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Unit Economics Brief",
            domain="operations",
            theme="unit-economics",
            lead=Candidate(unit=lead),
            supporting=supporting,
            readiness_score=readiness_score,
            why_this_now="Design briefs need economics before pricing and scope decisions.",
            merged_product_concept="A deterministic unit economics artifact for design briefs.",
            synthesis_rationale="Connect source ideas to price, cost, and payback assumptions.",
            mvp_scope=mvp_scope,
            first_milestones=["Return unit economics JSON"] if not sparse else [],
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id, *[candidate.unit.id for candidate in supporting]],
            design_status="approved",
        )
    )
    return store, brief_id


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=84.0,
        strengths=["clear buyer workflow"],
        weaknesses=["margin requires validation"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
