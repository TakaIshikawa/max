"""Tests for design brief compliance checklist generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_compliance_checklist import (
    SCHEMA_VERSION,
    build_design_brief_compliance_checklist,
    compliance_checklist_filename,
    render_design_brief_compliance_checklist,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_build_design_brief_compliance_checklist_sections_and_evidence(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_compliance_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    assert checklist["schema_version"] == SCHEMA_VERSION
    assert checklist["kind"] == "max.design_brief.compliance_checklist"
    assert checklist["design_brief"]["id"] == brief_id
    assert checklist["design_brief"]["source_idea_ids"] == [
        "bu-compliance-lead",
        "bu-compliance-support",
    ]
    assert checklist["summary"]["gate"] == "ready_for_compliance_review"
    assert [section["id"] for section in checklist["sections"]] == [
        "security",
        "privacy",
        "accessibility",
        "data_retention",
        "launch_governance",
    ]
    assert [item["id"] for item in checklist["checklist_items"]] == [
        f"DBCC{index}" for index in range(1, 11)
    ]
    assert all(item["source_idea_ids"] for item in checklist["checklist_items"])
    assert all("evidence_references" in item for item in checklist["checklist_items"])
    assert {ref["id"] for ref in checklist["evidence_references"]} >= {
        "sig-security",
        "sig-privacy",
        "ins-compliance",
    }

    security = next(section for section in checklist["sections"] if section["id"] == "security")
    assert any(ref["id"] == "sig-security" for ref in security["evidence_references"])
    assert json.loads(json.dumps(checklist))["design_brief"]["id"] == brief_id


def test_render_design_brief_compliance_checklist_markdown_json_and_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_compliance_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    markdown = render_design_brief_compliance_checklist(checklist, fmt="markdown")
    assert markdown.startswith("# Compliance Checklist: Compliance Checklist Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Security" in markdown
    assert "## Privacy" in markdown
    assert "## Accessibility" in markdown
    assert "## Data Retention" in markdown
    assert "## Launch Governance" in markdown
    assert "### DBCC1: Review authentication, authorization, and credential handling" in markdown
    assert "`sig-security`" in markdown
    assert "## Recommended Next Actions" in markdown

    parsed = json.loads(render_design_brief_compliance_checklist(checklist, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    with pytest.raises(ValueError, match="Unsupported compliance checklist format: yaml"):
        render_design_brief_compliance_checklist(checklist, fmt="yaml")


def test_build_design_brief_compliance_checklist_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_compliance_checklist.db"), wal_mode=True)
    try:
        checklist = build_design_brief_compliance_checklist(store, "dbf-missing")
    finally:
        store.close()

    assert checklist is None


def test_compliance_checklist_filename_uses_brief_id_and_title() -> None:
    assert (
        compliance_checklist_filename(
            {"id": "dbf-test001", "title": "Compliance Checklist API Brief"},
            fmt="markdown",
        )
        == "dbf-test001-Compliance-Checklist-API-Brief-compliance-checklist.md"
    )


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_compliance_checklist.db"), wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-security",
            source_type=SignalSourceType.SECURITY,
            source_adapter="nvd",
            title="Security credential risk",
            content="Credential handling and threat modeling are required.",
            url="https://example.com/sig-security",
            tags=["security", "risk"],
            metadata={"signal_role": "risk"},
        )
    )
    store.insert_signal(
        Signal(
            id="sig-privacy",
            source_type=SignalSourceType.REPORT,
            source_adapter="privacy_report",
            title="Privacy data notice",
            content="Customer personal data needs consent and clear notice.",
            url="https://example.com/sig-privacy",
            tags=["privacy", "data"],
            metadata={"signal_role": "privacy"},
        )
    )
    store.insert_insight(
        Insight(
            id="ins-compliance",
            category=InsightCategory.VULNERABILITY,
            title="Compliance launch governance gap",
            summary="Teams need explicit compliance approval before launch.",
            evidence=["sig-security"],
            confidence=0.82,
            domains=["developer-tools"],
        )
    )

    lead = BuildableUnit(
        id="bu-compliance-lead",
        title="Compliance Checklist Lead",
        one_liner="Gate design brief compliance before execution.",
        category="application",
        problem="Autonomous execution needs explicit compliance checks.",
        solution="Generate a deterministic compliance checklist from persisted design briefs.",
        value_proposition="Prevent specs from bypassing compliance review.",
        specific_user="implementation lead",
        buyer="engineering manager",
        workflow_context="design-to-spec handoff with customer telemetry",
        current_workaround="manual launch notes",
        why_now="Design briefs already generate handoff artifacts.",
        validation_plan="Review compliance checklist with security and privacy owners.",
        first_10_customers="internal implementation leads",
        domain_risks=["Credential handling and customer data retention may be unclear."],
        evidence_rationale="Evidence shows security and privacy launch gaps.",
        inspiring_insights=["ins-compliance"],
        evidence_signals=["sig-security", "sig-privacy"],
        tech_approach="FastAPI route using deterministic analysis code and persisted evidence.",
        suggested_stack={"language": "python", "framework": "fastapi"},
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-compliance-support",
        title="Compliance Checklist Support",
        one_liner="Track data retention and accessibility before launch.",
        category="application",
        problem="Teams miss non-functional launch checks.",
        solution="Attach source idea IDs and evidence references to compliance items.",
        value_proposition="Make compliance decisions auditable.",
        specific_user="product operator",
        buyer="product lead",
        workflow_context="launch governance review",
        validation_plan="Compare JSON and Markdown output.",
        domain_risks=["Data retention decisions can drift from source ideas."],
        evidence_signals=["sig-privacy"],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Compliance Checklist Brief",
            domain="developer-tools",
            theme="compliance-gate",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=87.0,
            why_this_now="Compliance needs to gate autonomous execution.",
            merged_product_concept="A compliance checklist export for persisted design briefs.",
            synthesis_rationale="Completes execution handoff governance.",
            mvp_scope=["JSON compliance checklist", "Markdown compliance checklist"],
            first_milestones=["Return compliance checklist JSON", "Return compliance checklist Markdown"],
            validation_plan="Confirm compliance checklist traceability with owners.",
            risks=["Compliance checklist may be treated as a substitute for legal review."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id
