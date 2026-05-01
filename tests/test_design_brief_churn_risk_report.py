from __future__ import annotations

import json

import pytest

from max.analysis import (
    build_design_brief_churn_risk_report as exported_build_churn_risk_report,
)
from max.analysis.design_brief_churn_risk_report import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_churn_risk_report,
    render_design_brief_churn_risk_report,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_churn_risk_report_high_risk_with_weak_evidence_and_friction(tmp_path) -> None:
    store = Store(str(tmp_path / "high_churn.db"))
    try:
        brief_id = _seed_high_risk_brief(store)
        report = build_design_brief_churn_risk_report(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["score"] >= 65
    assert report["tier"] == "high"
    assert report["summary"]["pricing_friction"] == "high"
    assert report["summary"]["support_burden"] == "high"
    assert [driver["id"] for driver in report["risk_drivers"]] == [
        "evidence_strength",
        "validation_status",
        "support_burden",
        "pricing_friction",
        "retention_value",
    ]
    assert report["follow_up_experiments"][0]["id"] == "EXP0"


def test_churn_risk_report_low_risk_with_validation_evidence_and_value(tmp_path) -> None:
    store = Store(str(tmp_path / "low_churn.db"))
    try:
        brief_id = _seed_low_risk_brief(store)
        report = build_design_brief_churn_risk_report(store, brief_id)
        repeated = build_design_brief_churn_risk_report(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["tier"] == "low"
    assert report["score"] < 35
    assert report["summary"]["evidence_reference_count"] >= 4
    assert report["risk_drivers"][0]["id"] == "no_major_driver"
    assert report["summary"]["validation_status"] == "approved"
    assert exported_build_churn_risk_report is build_design_brief_churn_risk_report


def test_churn_risk_report_missing_data_uses_fallbacks(tmp_path) -> None:
    store = Store(str(tmp_path / "missing_churn.db"))
    try:
        brief_id = _seed_missing_data_brief(store)
        report = build_design_brief_churn_risk_report(store, brief_id)
        missing = build_design_brief_churn_risk_report(store, "dbf-missing")
    finally:
        store.close()

    assert missing is None
    assert report is not None
    assert report["tier"] in {"medium", "high"}
    assert report["design_brief"]["buyer"] == ""
    assert report["design_brief"]["workflow_context"] == ""
    assert report["summary"]["evidence_reference_count"] == 0
    assert any(driver["id"] == "validation_status" for driver in report["risk_drivers"])
    assert report["warning_indicators"]
    assert report["retention_levers"]


def test_render_churn_risk_report_markdown_json_and_invalid_format(tmp_path) -> None:
    store = Store(str(tmp_path / "markdown_churn.db"))
    try:
        brief_id = _seed_high_risk_brief(store)
        report = build_design_brief_churn_risk_report(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_churn_risk_report(report, "markdown")

    assert markdown.startswith("# Churn Risk Report: High Churn Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Kind: `{KIND}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Risk Drivers" in markdown
    assert "## Retention Levers" in markdown
    assert "## Warning Indicators" in markdown
    assert "## Follow-Up Experiments" in markdown
    assert "## Dimension Scores" in markdown
    assert "## Evidence References" in markdown

    assert json.loads(render_design_brief_churn_risk_report(report, "json")) == report
    with pytest.raises(ValueError):
        render_design_brief_churn_risk_report(report, "yaml")


def _seed_high_risk_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-high-churn",
        title="High Churn Lead",
        one_liner="A risky enterprise migration helper.",
        category="application",
        problem="Teams struggle with manual migration handoff and security review.",
        solution="Coordinate integration setup.",
        value_proposition="Coordinate enterprise setup handoffs.",
        specific_user="platform operator",
        buyer="IT director",
        workflow_context="migration support workflow",
        current_workaround="manual support tickets",
        why_now="New compliance dependency creates urgent onboarding work.",
        validation_plan="",
        first_10_customers="enterprise platform teams",
        domain_risks=[
            "Procurement and budget approval may block paid conversion.",
            "Security integration support burden may create churn.",
        ],
        evidence_signals=[],
        inspiring_insights=[],
        domain="developer-tools",
        status="candidate",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="High Churn Brief",
            domain="developer-tools",
            theme="migration-risk",
            lead=Candidate(unit=lead),
            readiness_score=42.0,
            why_this_now="Teams need a migration workflow, but budget ownership is unclear.",
            merged_product_concept="A migration support helper for integration setup.",
            synthesis_rationale="Manual support, security dependency, and procurement risk remain unresolved.",
            mvp_scope=["Migration workflow", "Support dashboard", "Security checklist", "Integration setup"],
            first_milestones=["Run internal setup"],
            validation_plan="",
            risks=[
                "No budget owner for pricing approval.",
                "Support ticket burden could exceed onboarding capacity.",
            ],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )


def _seed_low_risk_brief(store: Store) -> str:
    signals = [
        Signal(
            id="sig-activation",
            source_type=SignalSourceType.SURVEY,
            source_adapter="survey",
            title="Activation evidence",
            content="Weekly workflow users report recurring value and renewal intent.",
            url="https://example.com/activation",
            tags=["workflow", "retention"],
            credibility=0.9,
            metadata={"signal_role": "workflow"},
        ),
        Signal(
            id="sig-buyer",
            source_type=SignalSourceType.MARKET,
            source_adapter="interview",
            title="Buyer evidence",
            content="Buyer confirms clear executive sponsorship and renewal path.",
            url="https://example.com/buyer",
            tags=["buyer", "renewal"],
            credibility=0.9,
            metadata={"signal_role": "buyer"},
        ),
        Signal(
            id="sig-value",
            source_type=SignalSourceType.REPORT,
            source_adapter="crm",
            title="Value evidence",
            content="Pilot reduced recurring workflow effort.",
            url="https://example.com/value",
            tags=["value", "workflow"],
            credibility=0.85,
            metadata={"signal_role": "validation"},
        ),
    ]
    for signal in signals:
        store.insert_signal(signal)
    store.insert_insight(
        Insight(
            id="ins-retention",
            category=InsightCategory.EMERGING_PATTERN,
            title="Retention signal",
            summary="Pilot teams use the workflow weekly and describe clear renewal value.",
            evidence=["sig-value"],
            confidence=0.86,
            domains=["developer-tools"],
        )
    )
    lead = BuildableUnit(
        id="bu-low-churn",
        title="Low Churn Lead",
        one_liner="Recurring workflow automation.",
        category="application",
        problem="Platform teams waste time on repeated release workflow checks.",
        solution="Automate a weekly release readiness workflow.",
        value_proposition="Save time, reduce manual review, and create recurring weekly habit.",
        specific_user="platform engineer",
        buyer="VP Engineering",
        workflow_context="weekly release readiness workflow",
        current_workaround="manual checklist",
        why_now="Teams now ship more frequent agent releases.",
        validation_plan="Run a paid pilot and measure weekly activation.",
        first_10_customers="10 platform teams",
        domain_risks=[],
        evidence_signals=["sig-activation", "sig-buyer"],
        inspiring_insights=["ins-retention"],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_evaluation(_evaluation(lead.id))
    return store.insert_design_brief(
        ProjectBrief(
            title="Low Churn Brief",
            domain="developer-tools",
            theme="retention",
            lead=Candidate(unit=lead),
            readiness_score=88.0,
            why_this_now="Weekly release review is becoming a recurring workflow.",
            merged_product_concept="Automation that saves time and reduces repeated manual checks.",
            synthesis_rationale="Evidence shows recurring use, buyer value, and approved validation.",
            mvp_scope=["Weekly activation report", "Value summary"],
            first_milestones=["Run paid pilot", "Measure renewal intent"],
            validation_plan="Measure weekly activation and buyer renewal proof in pilot.",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )


def _seed_missing_data_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-missing-churn",
        title="Missing Churn Lead",
        one_liner="Sparse idea",
        category="application",
        problem="",
        solution="",
        value_proposition="",
        specific_user="",
        buyer="",
        workflow_context="",
        validation_plan="",
        domain_risks=[],
        evidence_signals=[],
        inspiring_insights=[],
        domain="developer-tools",
        status="candidate",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Missing Churn Brief",
            domain="developer-tools",
            theme="retention",
            lead=Candidate(unit=lead),
            readiness_score=25.0,
            why_this_now="",
            merged_product_concept="",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="draft",
        )
    )


def _evaluation(unit_id: str) -> UtilityEvaluation:
    strong = DimensionScore(value=8.0, confidence=0.8, reasoning="validated")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=strong,
        addressable_scale=strong,
        build_effort=DimensionScore(value=4.0, confidence=0.8, reasoning="small"),
        composability=strong,
        competitive_density=DimensionScore(value=4.0, confidence=0.7, reasoning="some alternatives"),
        timing_fit=strong,
        compounding_value=strong,
        overall_score=86.0,
        strengths=["weekly recurring workflow", "clear buyer value"],
        weaknesses=[],
        recommendation="yes",
        weights_used={"timing_fit": 0.2},
    )
