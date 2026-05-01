"""Tests for portfolio regulatory exposure analysis."""

from __future__ import annotations

import json

from max.analysis import build_portfolio_regulatory_exposure_report as exported_report
from max.analysis.portfolio_regulatory_exposure import (
    SCHEMA_VERSION,
    build_portfolio_regulatory_exposure_from_records,
    build_portfolio_regulatory_exposure_report,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_regulatory_exposure_groups_briefs_from_actual_fields(store: Store) -> None:
    _insert_evidence(store)
    health = _unit(
        "bu-health",
        "Patient Intake Risk Reviewer",
        domain="healthcare",
        target_users="care coordinators handling patient records",
        buyer="hospital compliance buyer",
        specific_user="nurse manager",
        problem="Patient intake teams need HIPAA-safe review of clinical notes.",
        solution="Review medical intake notes and flag missing consent.",
        domain_risks=["HIPAA and patient privacy review required."],
        evidence_signals=["sig-privacy"],
        inspiring_insights=["ins-security"],
    )
    finance = _unit(
        "bu-finance",
        "Invoice Approval Monitor",
        domain="finops",
        target_users="finance operators",
        buyer="enterprise procurement buyer",
        specific_user="accounts payable analyst",
        problem="Payment approvals lack audit evidence.",
        solution="Monitor invoices, approvals, and vendor contract status.",
        domain_risks=["SOX audit and procurement approval may block rollout."],
        evidence_signals=["sig-procurement"],
    )
    security = _unit(
        "bu-security",
        "OAuth Scope Auditor",
        domain="security",
        target_users="security engineers",
        buyer="security platform lead",
        problem="Teams ship OAuth integrations without access-control review.",
        solution="Audit OAuth scopes, credentials, and secrets handling.",
        domain_risks=["Security threat model required."],
        evidence_signals=["sig-security"],
    )
    for unit in (health, finance, security):
        store.insert_buildable_unit(unit)

    health_brief_id = store.insert_design_brief(
        _brief(
            "Patient Intake Review",
            "healthcare",
            "patient-privacy",
            health,
            readiness=91.0,
            concept="A HIPAA-aware patient intake review workflow for clinical care teams.",
            risks=["Patient privacy and consent handling require legal review."],
            scope=["Patient records", "Consent audit trail"],
        )
    )
    finance_brief_id = store.insert_design_brief(
        _brief(
            "Invoice Approval Monitor",
            "finops",
            "invoice-governance",
            finance,
            readiness=84.0,
            concept="A finance workflow for payment approval, vendor review, and audit readiness.",
            risks=["Procurement and SOX evidence may delay enterprise pilots."],
            scope=["Invoice audit log", "Vendor approval checklist"],
        )
    )
    security_brief_id = store.insert_design_brief(
        _brief(
            "OAuth Scope Auditor",
            "security",
            "access-review",
            security,
            readiness=78.0,
            concept="A security auditor for OAuth scopes, credentials, and access control.",
            risks=["Secrets handling and threat model review are required."],
            scope=["OAuth scope review", "Credential handling checklist"],
        )
    )

    report = build_portfolio_regulatory_exposure_report(store)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.portfolio_regulatory_exposure"
    assert report["summary"]["design_brief_count"] == 3
    assert report["summary"]["exposed_brief_count"] == 3
    assert report["summary"]["exposure_bucket_count"] >= 5

    buckets = {bucket["regulatory_area"]: bucket for bucket in report["exposure_buckets"]}
    assert buckets["privacy"]["exposure_count"] == 1
    assert buckets["healthcare"]["representative_brief_ids"] == [health_brief_id]
    assert finance_brief_id in buckets["finance"]["representative_brief_ids"]
    assert finance_brief_id in buckets["procurement"]["representative_brief_ids"]
    assert security_brief_id in buckets["security"]["representative_brief_ids"]
    assert any(
        reason["brief_id"] == security_brief_id
        for reason in buckets["security"]["exposure_reasons"]
    )
    assert any(
        "Evidence" in reason["reason"]
        or "Risk fields" in reason["reason"]
        for reason in buckets["security"]["exposure_reasons"]
    )
    assert json.loads(json.dumps(report))["summary"]["design_brief_count"] == 3


def test_regulatory_exposure_reasons_come_from_fields_not_fixture_ids() -> None:
    report = build_portfolio_regulatory_exposure_from_records(
        design_briefs=[
            {
                "id": "custom-a",
                "title": "Generic Audit Workflow",
                "domain": "operations",
                "theme": "workflow",
                "readiness_score": 72.0,
                "buyer": "operations leader",
                "specific_user": "workflow analyst",
                "merged_product_concept": "Review payroll records and payment approvals.",
                "risks": ["Financial audit and privacy review are required."],
                "source_idea_ids": ["idea-a"],
                "evidence_documents": [
                    {
                        "id": "sig-a",
                        "title": "Payroll evidence",
                        "content": "Finance teams need SOX controls for payroll data.",
                        "tags": ["finance", "privacy"],
                    }
                ],
            }
        ]
    )

    buckets = {bucket["regulatory_area"]: bucket for bucket in report["exposure_buckets"]}
    assert set(buckets) >= {"finance", "privacy"}
    assert buckets["finance"]["representative_brief_ids"] == ["custom-a"]
    assert buckets["finance"]["exposure_reasons"][0]["matched_terms"]
    assert not any(
        "fixture" in reason["reason"].lower()
        for reason in buckets["finance"]["exposure_reasons"]
    )


def test_regulatory_exposure_sparse_portfolio_returns_low_exposure_summary() -> None:
    report = build_portfolio_regulatory_exposure_from_records(
        design_briefs=[
            {
                "id": "dbf-simple",
                "title": "Simple Notes Formatter",
                "domain": "productivity",
                "theme": "notes",
                "merged_product_concept": "Format meeting notes for internal planning.",
                "risks": [],
                "source_idea_ids": [],
            }
        ]
    )

    assert report["summary"] == {
        "design_brief_count": 1,
        "exposed_brief_count": 0,
        "low_exposure_brief_count": 1,
        "exposure_bucket_count": 0,
        "high_risk_bucket_count": 0,
        "medium_risk_bucket_count": 0,
        "low_risk_bucket_count": 0,
        "overall_exposure_level": "low",
    }
    assert report["exposure_buckets"] == []
    assert report["recommendations"][0]["priority"] == "low"


def test_regulatory_exposure_filters_domain_and_is_exported(store: Store) -> None:
    unit = _unit("bu-a11y", "Keyboard Flow Checker", domain="design")
    store.insert_buildable_unit(unit)
    brief_id = store.insert_design_brief(
        _brief(
            "Keyboard Flow Checker",
            "design",
            "accessibility",
            unit,
            readiness=66.0,
            concept="Check keyboard and screen reader coverage for onboarding forms.",
            risks=["Accessibility review required for WCAG conformance."],
            scope=["Keyboard navigation", "Screen reader labels"],
        )
    )

    report = exported_report(store, domain="design")

    assert report["filters"]["domain"] == ["design"]
    assert report["summary"]["design_brief_count"] == 1
    assert report["exposure_buckets"][0]["regulatory_area"] == "accessibility"
    assert report["exposure_buckets"][0]["representative_brief_ids"] == [brief_id]


def _insert_evidence(store: Store) -> None:
    store.insert_signal(
        Signal(
            id="sig-privacy",
            source_type=SignalSourceType.REPORT,
            source_adapter="privacy_report",
            title="Patient data privacy",
            content="Healthcare teams need patient consent and privacy controls.",
            url="https://example.test/privacy",
            tags=["privacy", "healthcare"],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-procurement",
            source_type=SignalSourceType.REPORT,
            source_adapter="buyer_report",
            title="Procurement blockers",
            content="Enterprise buyers require vendor review, pricing, and contract approval.",
            url="https://example.test/procurement",
            tags=["procurement", "finance"],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-security",
            source_type=SignalSourceType.SECURITY,
            source_adapter="security_review",
            title="OAuth security review",
            content="OAuth credentials and access control need security review.",
            url="https://example.test/security",
            tags=["security", "oauth"],
        )
    )
    store.insert_insight(
        Insight(
            id="ins-security",
            category=InsightCategory.VULNERABILITY,
            title="Security review needed",
            summary="Security and privacy owners need explicit approval evidence.",
            evidence=["sig-security"],
            confidence=0.8,
            domains=["security"],
            implications=["Add security review before launch."],
        )
    )


def _unit(
    unit_id: str,
    title: str,
    *,
    domain: str,
    target_users: str = "product operators",
    buyer: str = "product leader",
    specific_user: str = "operator",
    problem: str = "Teams need deterministic review.",
    solution: str = "Generate a structured review.",
    domain_risks: list[str] | None = None,
    evidence_signals: list[str] | None = None,
    inspiring_insights: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=f"{title} for regulated workflows",
        category=BuildableCategory.APPLICATION,
        problem=problem,
        solution=solution,
        target_users=target_users,
        value_proposition="Prioritize review before execution.",
        specific_user=specific_user,
        buyer=buyer,
        workflow_context="regulated workflow review",
        validation_plan="Review with owners.",
        domain_risks=domain_risks or [],
        evidence_signals=evidence_signals or [],
        inspiring_insights=inspiring_insights or [],
        quality_score=7.0,
        usefulness_score=7.0,
        status="approved",
        domain=domain,
    )


def _brief(
    title: str,
    domain: str,
    theme: str,
    lead: BuildableUnit,
    *,
    readiness: float,
    concept: str,
    risks: list[str],
    scope: list[str],
) -> ProjectBrief:
    return ProjectBrief(
        title=title,
        domain=domain,
        theme=theme,
        lead=Candidate(unit=lead, readiness_score=readiness),
        readiness_score=readiness,
        why_this_now="Review gates must be explicit before execution.",
        merged_product_concept=concept,
        synthesis_rationale="Source fields indicate regulatory review needs.",
        mvp_scope=scope,
        first_milestones=["Prepare review checklist"],
        validation_plan="Validate with legal, compliance, or security owners.",
        risks=risks,
        source_idea_ids=[lead.id],
        design_status="approved",
    )
