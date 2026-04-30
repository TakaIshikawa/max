from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_security_review_plan import (
    SCHEMA_VERSION,
    build_design_brief_security_review_plan,
    render_design_brief_security_review_plan,
    security_review_plan_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_build_design_brief_security_review_plan_is_deterministic_and_complete(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "security_review_plan.db"), wal_mode=True)
    try:
        brief_id = _seed_security_brief(store)
        first = build_design_brief_security_review_plan(store, brief_id)
        second = build_design_brief_security_review_plan(store, brief_id)
    finally:
        store.close()

    assert first is not None
    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.security_review_plan"
    assert first["design_brief"]["id"] == brief_id
    assert first["design_brief"]["source_idea_ids"] == ["bu-security-lead", "bu-security-support"]
    assert first["summary"]["risk_count"] >= 4
    assert first["summary"]["check_count"] >= 5
    assert first["threat_model_scope"]["assets"]
    assert first["threat_model_scope"]["entry_points"]
    assert any(item["name"] == "OAuth tokens" for item in first["sensitive_data"])
    assert any(item["name"] == "GitHub" for item in first["integration_risks"])
    assert any("least privilege" in item["mitigation"] for item in first["abuse_cases"])
    assert [check["id"] for check in first["security_acceptance_checks"]][:5] == [
        "SRC1",
        "SRC2",
        "SRC3",
        "SRC4",
        "SRC5",
    ]
    assert {ref["id"] for ref in first["evidence_references"]} == {
        "ins-security-review",
        "sig-security-review",
    }
    assert json.loads(json.dumps(first))["design_brief"]["id"] == brief_id


def test_sparse_design_brief_security_review_plan_reports_unknowns_and_gaps(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "sparse_security_review_plan.db"), wal_mode=True)
    try:
        brief_id = _seed_sparse_brief(store)
        report = build_design_brief_security_review_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    gap_text = [gap["gap"] for gap in report["evidence_gaps"]]
    assert "Workflow boundaries are not explicit." in gap_text
    assert "MVP scope is not decomposed for review." in gap_text
    assert "Validation plan is missing security review criteria." in gap_text
    assert "No security, privacy, risk, or compliance evidence is linked." in gap_text
    assert any(gap["kind"] == "unknown" for gap in report["evidence_gaps"])
    assert report["summary"]["review_gate"] == "needs_security_discovery"
    assert report["open_questions"]


def test_render_design_brief_security_review_plan_json_markdown_and_invalid_format(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "render_security_review_plan.db"), wal_mode=True)
    try:
        brief_id = _seed_security_brief(store)
        report = build_design_brief_security_review_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    parsed = json.loads(render_design_brief_security_review_plan(report, fmt="json"))
    assert parsed == report

    markdown = render_design_brief_security_review_plan(report, fmt="markdown")
    assert markdown.startswith("# Security Review Plan: Security Review Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Review Scope" in markdown
    assert "## Risks" in markdown
    assert "### Sensitive Data" in markdown
    assert "### Integration Risks" in markdown
    assert "### Abuse Cases" in markdown
    assert "## Checks" in markdown
    assert "## Evidence Gaps" in markdown
    assert "## Open Questions" in markdown
    assert "### SRC1: Threat model scope is accepted" in markdown

    with pytest.raises(ValueError, match="Unsupported security review plan format: yaml"):
        render_design_brief_security_review_plan(report, fmt="yaml")


def test_build_design_brief_security_review_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_security_review_plan.db"), wal_mode=True)
    try:
        report = build_design_brief_security_review_plan(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def test_security_review_plan_filename_uses_brief_id_and_title() -> None:
    assert (
        security_review_plan_filename(
            {"id": "dbf-test001", "title": "Security Review API Brief"},
            fmt="markdown",
        )
        == "dbf-test001-Security-Review-API-Brief-security-review-plan.md"
    )
    assert (
        security_review_plan_filename(
            {"id": "dbf-test001", "title": "Security Review API Brief"},
            fmt="json",
        )
        == "dbf-test001-Security-Review-API-Brief-security-review-plan.json"
    )


def _seed_security_brief(store: Store) -> str:
    store.insert_signal(
        Signal(
            id="sig-security-review",
            source_type=SignalSourceType.SECURITY,
            source_adapter="nvd",
            title="OAuth security review evidence",
            content="Credential scope, token storage, privacy, and abuse review are required.",
            url="https://example.com/security-review",
            tags=["security", "oauth", "risk"],
            metadata={"signal_role": "risk"},
        )
    )
    store.insert_insight(
        Insight(
            id="ins-security-review",
            category=InsightCategory.VULNERABILITY,
            title="Autonomous build security gate",
            summary="Specs handed to autonomous builders need threat review and acceptance checks.",
            evidence=["sig-security-review"],
            confidence=0.88,
            domains=["developer-tools"],
        )
    )

    lead = BuildableUnit(
        id="bu-security-lead",
        title="Security Review Lead",
        one_liner="Gate autonomous specs with a security review plan.",
        category="application",
        problem="Autonomous builders need explicit security review before execution.",
        solution="Generate threat scope, abuse cases, and security checks from design briefs.",
        value_proposition="Prevent unsafe implementation handoffs.",
        specific_user="platform security engineer",
        buyer="engineering manager",
        workflow_context="design-to-build handoff with customer workflow data and telemetry",
        current_workaround="manual security review notes",
        why_now="Generated specs are increasingly assigned to agents.",
        validation_plan="Review generated checks with security and product owners.",
        domain_risks=["OAuth tokens and GitHub repository permissions may be over-scoped."],
        evidence_rationale="Security evidence highlights credential and abuse risk.",
        inspiring_insights=["ins-security-review"],
        evidence_signals=["sig-security-review"],
        tech_approach="FastAPI endpoint with GitHub API integration, OAuth token storage, and audit logging.",
        suggested_stack={"language": "python", "framework": "fastapi", "integration": "github api"},
        domain="developer-tools",
        status="approved",
    )
    support = BuildableUnit(
        id="bu-security-support",
        title="Security Review Support",
        one_liner="Track security checks for generated implementation plans.",
        category="application",
        problem="Teams miss security acceptance criteria during handoff.",
        solution="Attach source evidence to security review output.",
        value_proposition="Make security decisions traceable.",
        specific_user="implementation lead",
        buyer="product lead",
        workflow_context="agent build request with customer feedback data",
        validation_plan="Compare JSON and Markdown output.",
        domain_risks=["Telemetry may include PII if fixtures are copied from customers."],
        evidence_signals=["sig-security-review"],
        tech_approach="JSON and Markdown renderer for API and MCP consumers.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    return store.insert_design_brief(
        ProjectBrief(
            title="Security Review Plan Brief",
            domain="developer-tools",
            theme="security-review",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=84.0,
            why_this_now="Generated implementation specs need security review before autonomous execution.",
            merged_product_concept="A security review plan artifact for persisted design briefs.",
            synthesis_rationale="Combines security evidence and implementation handoff risk.",
            mvp_scope=["JSON security review plan", "Markdown security review plan"],
            first_milestones=["Return structured security plan", "Render stable Markdown"],
            validation_plan="Confirm threat model checks with security owner.",
            risks=["GitHub OAuth scopes and customer telemetry can expose sensitive data."],
            source_idea_ids=[lead.id, support.id],
            design_status="approved",
        )
    )


def _seed_sparse_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-security-sparse",
        title="Sparse Security Review Lead",
        one_liner="Sparse security review idea.",
        category="application",
        problem="Review is needed.",
        solution="Create a security plan.",
        value_proposition="Reduce risk.",
        specific_user="",
        buyer="",
        workflow_context="",
        validation_plan="",
        domain_risks=[],
        evidence_signals=[],
        tech_approach="",
        suggested_stack={},
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Sparse Security Review Brief",
            domain="developer-tools",
            theme="security-review",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=41.0,
            why_this_now="",
            merged_product_concept="",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
