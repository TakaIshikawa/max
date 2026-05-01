from __future__ import annotations

import json

import pytest

from max.analysis import build_design_brief_privacy_impact_assessment as exported_build
from max.analysis import render_design_brief_privacy_impact_assessment as exported_render
from max.analysis.design_brief_privacy_impact_assessment import (
    SCHEMA_VERSION,
    build_design_brief_privacy_impact_assessment,
    render_design_brief_privacy_impact_assessment,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _unit(
    unit_id: str,
    *,
    domain: str = "healthcare",
    buyer: str = "hospital compliance lead",
    specific_user: str = "care coordinator",
    workflow_context: str = "patient discharge planning workflow with clinical notes",
    domain_risks: list[str] | None = None,
    evidence_signals: list[str] | None = None,
    why_now: str = "Healthcare buyers expect privacy review before pilot.",
    tech_approach: str = "Python API with EHR integration and audit logs.",
    suggested_stack: dict[str, str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Privacy Source {unit_id}",
        one_liner="Privacy source idea",
        category="application",
        problem="Teams need safer handoffs for sensitive workflow data.",
        solution="Assess privacy obligations before build.",
        value_proposition="Reduce privacy and launch risk.",
        specific_user=specific_user,
        buyer=buyer,
        workflow_context=workflow_context,
        current_workaround="manual spreadsheet review",
        why_now=why_now,
        validation_plan="Run discovery with synthetic patient examples.",
        domain_risks=domain_risks if domain_risks is not None else ["Patient data may include HIPAA-regulated PII."],
        evidence_signals=evidence_signals if evidence_signals is not None else ["sig-privacy"],
        tech_approach=tech_approach,
        suggested_stack=suggested_stack if suggested_stack is not None else {"language": "python", "integration": "EHR API"},
        domain=domain,
        status="approved",
    )


def _seed_privacy_brief(store: Store) -> str:
    store.insert_signal(
        Signal(
            id="sig-privacy",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Privacy assessment evidence",
            content="Buyers want privacy gates for patient workflow data.",
            url="https://example.com/privacy",
            tags=["privacy"],
            credibility=0.9,
        )
    )
    lead = _unit("bu-privacy-lead")
    support = _unit(
        "bu-privacy-support",
        workflow_context="handoff workflow that uses patient records and appointment telemetry",
        domain_risks=["Vendor integration may expose patient identifiers."],
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    return store.insert_design_brief(
        ProjectBrief(
            title="Care Handoff Privacy Brief",
            domain="healthcare",
            theme="care-coordination",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=82.0,
            why_this_now="Care teams need privacy-safe automation now.",
            merged_product_concept="Coordinate discharge handoffs using patient records and generated summaries.",
            synthesis_rationale="Combines source ideas for a regulated healthcare workflow.",
            mvp_scope=["Patient handoff summary", "Audit log export", "EHR API integration"],
            first_milestones=["Map data flow", "Implement role-based access"],
            validation_plan="Run pilot with synthetic patient data before real records.",
            risks=["Patient data may include PII and requires privacy review."],
            source_idea_ids=["bu-privacy-lead", "bu-privacy-support"],
        )
    )


def test_build_design_brief_privacy_impact_assessment_is_stable_and_complete(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_privacy_brief(store)
        first = build_design_brief_privacy_impact_assessment(store, brief_id)
        second = build_design_brief_privacy_impact_assessment(store, brief_id)
    finally:
        store.close()

    assert first is not None
    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["design_brief"]["id"] == brief_id
    assert first["design_brief"]["source_idea_ids"] == ["bu-privacy-lead", "bu-privacy-support"]
    assert first["summary"]["sensitive_data_expected"] is True
    assert first["summary"]["privacy_gate"] == "privacy_review_required"

    category_ids = [category["id"] for category in first["data_categories"]]
    assert "regulated_sensitive_data" in category_ids
    assert "workflow_content" in category_ids
    assert "telemetry_and_usage" in category_ids
    assert "third_party_data" in category_ids

    purpose_ids = [purpose["id"] for purpose in first["processing_purposes"]]
    assert purpose_ids == [
        "core_workflow_delivery",
        "validation_and_research",
        "security_and_audit",
        "buyer_readiness",
    ]
    assert all(purpose["data_category_ids"] for purpose in first["processing_purposes"])
    assert any(risk["severity"] == "high" for risk in first["risk_areas"])
    assert any(mitigation["id"] == "M6" for mitigation in first["mitigations"])
    assert first["open_questions"] == []
    assert any(gate["status"] == "blocked" for gate in first["launch_gates"])
    assert all(owner["role"] for owner in first["owners"])


def test_build_design_brief_privacy_impact_assessment_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_privacy_impact_assessment(store, "dbf-missing") is None
    finally:
        store.close()


def test_privacy_impact_assessment_sparse_brief_has_actionable_questions(tmp_path) -> None:
    lead = _unit(
        "bu-privacy-sparse",
        domain="",
        buyer="",
        specific_user="",
        workflow_context="",
        domain_risks=[],
        evidence_signals=[],
        why_now="",
        tech_approach="",
        suggested_stack={},
    )
    store = Store(str(tmp_path / "max.db"))
    try:
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Sparse Privacy Brief",
                domain="",
                theme="",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=20.0,
                why_this_now="",
                merged_product_concept="",
                synthesis_rationale="",
                mvp_scope=[],
                first_milestones=[],
                validation_plan="",
                risks=[],
                source_idea_ids=["bu-privacy-sparse"],
            )
        )
        report = build_design_brief_privacy_impact_assessment(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["privacy_gate"] == "needs_privacy_discovery"
    assert [category["id"] for category in report["data_categories"]] == [
        "workflow_content",
        "telemetry_and_usage",
        "evidence_and_research",
    ]
    assert report["data_categories"][0]["collection_status"] == "unknown_pending_mvp_scope"
    questions = [question["question"] for question in report["open_questions"]]
    assert "Who is the buyer or customer instruction owner for privacy decisions?" in questions
    assert "What data enters, leaves, and persists in the target workflow?" in questions
    assert "Which MVP actions require personal, customer, telemetry, or evidence data?" in questions
    assert any(gate["status"] == "blocked" for gate in report["launch_gates"])


def test_render_design_brief_privacy_impact_assessment_json_and_markdown(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_privacy_brief(store)
        report = build_design_brief_privacy_impact_assessment(store, brief_id)
    finally:
        store.close()

    assert report is not None
    parsed = json.loads(render_design_brief_privacy_impact_assessment(report, "json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_privacy_impact_assessment(report, "markdown")
    assert markdown.startswith("# Privacy Impact Assessment: Care Handoff Privacy Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Data Categories" in markdown
    assert "## Processing Purposes" in markdown
    assert "## Privacy Risks" in markdown
    assert "## Mitigations" in markdown
    assert "## Open Questions" in markdown
    assert "## Launch Gates" in markdown
    assert "### regulated_sensitive_data: Regulated or sensitive data" in markdown

    with pytest.raises(ValueError):
        render_design_brief_privacy_impact_assessment(report, "yaml")


def test_design_brief_privacy_impact_assessment_is_importable_from_analysis_package(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_privacy_brief(store)
        report = exported_build(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = exported_render(report)
    assert report["risk_areas"][0]["id"] == "PR1"
    assert markdown.startswith("# Privacy Impact Assessment: Care Handoff Privacy Brief")
