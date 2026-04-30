"""Tests for design brief stakeholder map generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_stakeholder_map import (
    SCHEMA_VERSION,
    build_design_brief_stakeholder_map,
    render_design_brief_stakeholder_map,
    stakeholder_map_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_build_design_brief_stakeholder_map_roles_confidence_and_evidence(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_stakeholder_map(store, brief_id)
        repeated = build_design_brief_stakeholder_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.stakeholder_map"
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["buyer"] == "VP of Engineering"
    assert report["design_brief"]["specific_user"] == "platform engineer"
    assert report["design_brief"]["source_idea_ids"] == [
        "bu-stakeholder-lead",
        "bu-stakeholder-support",
    ]
    assert [stakeholder["role"] for stakeholder in report["stakeholders"]] == [
        "buyer",
        "user",
        "economic_buyer",
        "implementer",
        "approver",
        "blocker",
        "champion",
    ]
    assert report["summary"]["stakeholder_count"] == 7
    assert report["summary"]["evaluation_count"] == 2
    assert report["confidence"]["level"] in {"medium", "high"}
    assert [reference["id"] for reference in report["evidence_references"]] == [
        "sig-approval",
        "sig-budget",
        "sig-user-pain",
    ]
    assert report["evaluations"][0]["source_idea_id"] == "bu-stakeholder-lead"

    roles = {stakeholder["role"]: stakeholder for stakeholder in report["stakeholders"]}
    assert roles["buyer"]["persona"] == "VP of Engineering"
    assert roles["user"]["persona"] == "platform engineer"
    assert roles["economic_buyer"]["persona"] == "VP of Engineering"
    assert roles["implementer"]["persona"] == "platform engineer"
    assert roles["approver"]["persona"] == "security or compliance approver"
    assert roles["blocker"]["persona"] == "security, compliance, or procurement blocker"
    assert roles["champion"]["persona"] == "platform engineer"
    assert roles["buyer"]["responsibilities"]
    assert roles["approver"]["assumptions"]
    assert "sig-approval" in roles["approver"]["evidence_reference_ids"]
    assert "sig-budget" in roles["economic_buyer"]["evidence_reference_ids"]
    assert "sig-user-pain" in roles["user"]["evidence_reference_ids"]
    assert report["unresolved_assumptions"]
    assert any("approve budget" in question for question in report["interview_questions"])
    assert json.loads(json.dumps(report))["schema_version"] == SCHEMA_VERSION


def test_render_design_brief_stakeholder_map_markdown_json_and_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_stakeholder_map(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_stakeholder_map(report, fmt="markdown")
    assert markdown.startswith("# Stakeholder Map: Stakeholder Map Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "### Buyer: VP of Engineering" in markdown
    assert "### User: platform engineer" in markdown
    assert "### Approver: security or compliance approver" in markdown
    assert "- Responsibilities:" in markdown
    assert "- Assumptions:" in markdown
    assert "`sig-approval`" in markdown
    assert "## Interview Questions" in markdown
    assert "## Evidence References" in markdown

    parsed = json.loads(render_design_brief_stakeholder_map(report, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    with pytest.raises(ValueError, match="Unsupported stakeholder map format: yaml"):
        render_design_brief_stakeholder_map(report, fmt="yaml")


def test_build_design_brief_stakeholder_map_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_stakeholder_map.db"), wal_mode=True)
    try:
        report = build_design_brief_stakeholder_map(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def test_stakeholder_map_filename_uses_brief_id_and_title() -> None:
    assert (
        stakeholder_map_filename(
            {"id": "dbf-test001", "title": "Stakeholder Map API Brief"},
            fmt="markdown",
        )
        == "dbf-test001-Stakeholder-Map-API-Brief-stakeholder-map.md"
    )
    assert (
        stakeholder_map_filename(
            {"id": "dbf-test001", "title": "Stakeholder Map API Brief"},
            fmt="json",
        )
        == "dbf-test001-Stakeholder-Map-API-Brief-stakeholder-map.json"
    )


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_stakeholder_map.db"), wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-budget",
            source_type=SignalSourceType.FUNDING,
            source_adapter="budget_report",
            title="Budget owner purchase intent",
            content="Engineering leaders have budget for release workflow governance.",
            url="https://example.com/sig-budget",
            tags=["budget", "buyer"],
            credibility=0.86,
            metadata={"signal_role": "budget"},
        )
    )
    store.insert_signal(
        Signal(
            id="sig-user-pain",
            source_type=SignalSourceType.SURVEY,
            source_adapter="survey",
            title="Platform engineer workflow pain",
            content="Users report manual release reviews and unclear adoption paths.",
            url="https://example.com/sig-user-pain",
            tags=["user", "workflow", "pain"],
            credibility=0.82,
            metadata={"signal_role": "problem"},
        )
    )
    store.insert_signal(
        Signal(
            id="sig-approval",
            source_type=SignalSourceType.SECURITY,
            source_adapter="security_review",
            title="Security approval risk",
            content="Security approval and procurement review can block rollout.",
            url="https://example.com/sig-approval",
            tags=["security", "approval", "risk"],
            credibility=0.8,
            metadata={"signal_role": "risk"},
        )
    )
    store.insert_insight(
        Insight(
            id="ins-stakeholder",
            category=InsightCategory.EMERGING_PATTERN,
            title="Approval path needs stakeholder mapping",
            summary="Teams need buyer, user, and approval owners before pilots.",
            evidence=["sig-approval"],
            confidence=0.78,
            domains=["developer-tools"],
        )
    )

    lead = BuildableUnit(
        id="bu-stakeholder-lead",
        title="Stakeholder Release Map",
        one_liner="Map stakeholders for release governance pilots.",
        category="application",
        problem="Platform teams do not know who must approve release governance pilots.",
        solution="Generate a stakeholder map from persisted design brief lineage.",
        value_proposition="Make buyer, user, approver, and blocker assumptions explicit.",
        specific_user="platform engineer",
        buyer="VP of Engineering",
        workflow_context="agent release governance review",
        current_workaround="manual release notes and ad hoc approval chats",
        why_now="Agent release reviews are becoming a recurring governance workflow.",
        validation_plan="Interview platform engineers, security approvers, and engineering buyers.",
        first_10_customers="platform teams shipping production agents",
        domain_risks=["Security approval and procurement review may block rollout."],
        evidence_rationale="Evidence shows user pain, budget ownership, and approval risk.",
        evidence_signals=["sig-budget", "sig-user-pain"],
        inspiring_insights=["ins-stakeholder"],
        tech_approach="Deterministic Python report over persisted Store records.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-stakeholder-support",
        title="Stakeholder Interview Plan",
        one_liner="Ask validation questions for buyer and approver roles.",
        category="application",
        problem="Discovery skips economic buyer and blocker validation.",
        solution="Recommend interview questions by stakeholder role.",
        value_proposition="Improve GTM validation before implementation.",
        specific_user="product operator",
        buyer="product lead",
        workflow_context="pilot stakeholder discovery",
        validation_plan="Validate champion access and approval gates.",
        domain_risks=["Champion may not control budget."],
        evidence_signals=["sig-user-pain"],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    store.insert_evaluation(_evaluation(lead.id, 86.0))
    store.insert_evaluation(_evaluation(support.id, 78.0))

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Stakeholder Map Brief",
            domain="developer-tools",
            theme="stakeholder-validation",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=88.0,
            why_this_now="Release governance pilots need named buyer, user, approver, and blocker roles.",
            merged_product_concept="A deterministic stakeholder map export for design briefs.",
            synthesis_rationale="Source ideas show GTM validation gaps around stakeholder ownership.",
            mvp_scope=["JSON stakeholder map", "Markdown stakeholder map"],
            first_milestones=["Build deterministic stakeholder report"],
            validation_plan="Run interviews with buyer, user, economic buyer, approver, blocker, and champion.",
            risks=["Security approval and procurement review may block rollout."],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _evaluation(unit_id: str, overall_score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=DimensionScore(value=5.0, confidence=0.7, reasoning="some alternatives"),
        timing_fit=dim,
        compounding_value=dim,
        overall_score=overall_score,
        strengths=["clear stakeholder"],
        weaknesses=["approval path needs validation"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
