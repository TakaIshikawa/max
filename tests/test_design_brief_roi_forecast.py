"""Tests for design brief ROI forecast generation."""

from __future__ import annotations

import csv
from io import StringIO
import json

import pytest

from max.analysis.design_brief_roi_forecast import (
    CSV_COLUMNS,
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


def test_render_design_brief_roi_forecast_csv_populated_rows(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_roi_forecast(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_roi_forecast(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert {row["design_brief_id"] for row in rows} == {brief_id}
    assert {row["design_brief_title"] for row in rows} == {"ROI Forecast Brief"}
    assert [row["row_type"] for row in rows[:3]] == ["assumption"] * 3
    assert "implementation_cost_component" in {row["row_type"] for row in rows}
    assert "benefit_component" in {row["row_type"] for row in rows}
    assert "payback_range" in {row["row_type"] for row in rows}
    assert "confidence" in {row["row_type"] for row in rows}
    assert "evidence_reference" in {row["row_type"] for row in rows}
    assert "next_action" in {row["row_type"] for row in rows}

    evidence_ids = {item["id"] for item in report["evidence_references"]}
    cost_row = next(row for row in rows if row["item_id"] == "engineering_delivery")
    assert cost_row["low_usd"] == str(
        next(
            item["low_usd"]
            for item in report["implementation_cost_bands"]["components"]
            if item["id"] == "engineering_delivery"
        )
    )
    assert set(cost_row["source_reference_ids"].split("; ")) == evidence_ids

    payback_row = next(row for row in rows if row["row_type"] == "payback_range")
    assert payback_row["expected_months"] == str(report["payback_range"]["expected_months"])
    assert payback_row["basis"] == report["payback_range"]["basis"]

    confidence_row = next(row for row in rows if row["row_type"] == "confidence")
    assert confidence_row["confidence_score"] == str(report["confidence_level"]["score"])
    assert confidence_row["confidence_level"] == report["confidence_level"]["level"]


def test_render_design_brief_roi_forecast_csv_sparse_without_evidence(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_roi_forecast(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rows = list(csv.DictReader(StringIO(render_design_brief_roi_forecast(report, fmt="csv"))))

    assert {row["design_brief_id"] for row in rows} == {brief_id}
    assert not [row for row in rows if row["row_type"] == "evidence_reference"]
    assert any(row["item_id"] == "A4" for row in rows)
    assert any(row["item_id"] == "thin_evidence_discount" for row in rows)
    assert all(row["source_reference_ids"] == "" for row in rows)
    assert rows[-1]["row_type"] == "next_action"


def test_render_design_brief_roi_forecast_csv_is_deterministic(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_roi_forecast(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert render_design_brief_roi_forecast(report, fmt="csv") == render_design_brief_roi_forecast(
        report,
        fmt="csv",
    )


def test_render_design_brief_roi_forecast_csv_numeric_formatting(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_roi_forecast(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rows = list(csv.DictReader(StringIO(render_design_brief_roi_forecast(report, fmt="csv"))))

    money_rows = [
        row
        for row in rows
        if row["row_type"]
        in {
            "implementation_cost_component",
            "implementation_cost_total",
            "benefit_component",
            "benefit_total",
        }
    ]
    assert money_rows
    assert all(row["low_usd"].isdigit() for row in money_rows)
    assert all(row["high_usd"].isdigit() for row in money_rows)
    assert all("$" not in row["low_usd"] and "," not in row["low_usd"] for row in money_rows)

    payback_row = next(row for row in rows if row["row_type"] == "payback_range")
    assert payback_row["expected_months"].isdigit()


def test_render_design_brief_roi_forecast_csv_escapes_special_characters() -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.roi_forecast",
        "design_brief": {"id": "dbf,csv", "title": 'ROI "Forecast"\nBrief'},
        "assumptions": [
            {
                "id": "A,1",
                "assumption": 'Validate "buyer", workflow\nand benefit.',
                "basis": "interview, notes",
            }
        ],
        "implementation_cost_bands": {
            "components": [
                {
                    "id": "cost,1",
                    "name": 'Engineering "delivery"',
                    "low_usd": 12000,
                    "high_usd": 24000,
                    "rationale": 'Scope includes export, review\nand "handoff".',
                }
            ],
            "total": {"low_usd": 12000, "high_usd": 24000},
        },
        "benefit_bands": {
            "components": [],
            "total_annual_benefit": {"low_usd": 0, "high_usd": 0},
        },
        "payback_range": {"expected_months": 12, "basis": "Cost / benefit."},
        "confidence_level": {
            "level": "low",
            "score": 42,
            "rationale": 'Needs "more", evidence.',
        },
        "evidence_references": [
            {"id": "ref,1", "type": "note", "description": 'Line one\n"line two"'}
        ],
        "next_actions": ['Run "pilot", then\ncompare costs.'],
    }

    csv_text = render_design_brief_roi_forecast(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert rows[0]["design_brief_title"] == 'ROI "Forecast"\nBrief'
    assert rows[0]["item_name"] == 'Validate "buyer", workflow\nand benefit.'
    assert rows[-1]["action_text"] == 'Run "pilot", then\ncompare costs.'
    assert '"ROI ""Forecast""\nBrief"' in csv_text
    assert '"Validate ""buyer"", workflow\nand benefit."' in csv_text


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
    assert (
        roi_forecast_filename(brief, fmt="csv")
        == "dbf-roi-001-ROI-Forecast-API-Brief-roi-forecast.csv"
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
