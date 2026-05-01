from __future__ import annotations

from max.spec import generate_security_review as exported_generate
from max.spec import render_security_review_markdown as exported_render
from max.spec.security_review import (
    SECURITY_REVIEW_SCHEMA_VERSION,
    generate_security_review,
    render_security_review_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-sec",
            "status": "approved",
            "domain": "customer-success",
            "category": "application",
        },
        "project": {
            "title": "Renewal Risk Console",
            "summary": "Coordinate renewal escalations across Salesforce and Slack.",
            "value_proposition": "Prevent missed customer renewal risks.",
            "target_users": "customer success teams",
            "specific_user": "customer success operator",
            "buyer": "customer success director",
            "workflow_context": "Salesforce account review to Slack renewal alert",
        },
        "problem": {
            "statement": "Teams copy customer account data into Slack without audit review.",
            "current_workaround": "Manual Salesforce exports and Slack messages with customer emails.",
            "why_now": "OAuth automation is moving into implementation handoffs.",
        },
        "solution": {
            "approach": "Sync Salesforce risk fields and post Slack workflow updates.",
            "technical_approach": (
                "FastAPI webhook API with OAuth, SSO, scoped tokens, RBAC roles, "
                "audit logs, rate limits, and encrypted secret storage."
            ),
            "suggested_stack": {
                "backend": "FastAPI",
                "crm": "Salesforce",
                "messaging": "Slack",
                "auth": "OAuth",
                "database": "Postgres",
            },
        },
        "execution": {
            "mvp_scope": [
                "Salesforce account sync",
                "Slack renewal notification",
                "Admin role review for customer data exports",
            ],
            "validation_plan": "Run OAuth sandbox sync, webhook signature checks, and audit log review.",
            "risks": [
                "Customer data retention and deletion rules may block launch.",
                "Salesforce API outages may delay Slack alerts.",
            ],
        },
        "evaluation": {
            "overall_score": 88.0,
            "recommendation": "yes",
            "weaknesses": ["Security and privacy review is required before production data access."],
        },
        "acceptance_criteria": {
            "functional_criteria": [
                {"id": "AC-F1", "statement": "Operator can send a Slack alert."},
            ],
            "non_functional_criteria": [
                {"id": "AC-NF1", "statement": "Secrets are redacted from logs."},
            ],
        },
    }


def test_generate_security_review_is_deterministic_and_complete_for_rich_specs() -> None:
    first = generate_security_review(_rich_tact_spec())
    second = generate_security_review(_rich_tact_spec())

    assert first == second
    assert first["schema_version"] == SECURITY_REVIEW_SCHEMA_VERSION
    assert first["kind"] == "max.security_review"
    assert first["source"]["idea_id"] == "bu-sec"
    assert first["summary"]["title"] == "Renewal Risk Console"
    assert first["summary"]["stack"] == (
        "auth=OAuth, backend=FastAPI, crm=Salesforce, database=Postgres, messaging=Slack"
    )
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "security_context",
        "findings",
        "recommended_controls",
        "open_questions",
    }
    assert {finding["category"] for finding in first["findings"]} == {
        "authentication",
        "authorization",
        "secret_handling",
        "data_retention",
        "dependency_exposure",
        "audit_logging",
        "abuse_cases",
    }
    assert first["summary"]["finding_count"] == 7
    assert first["summary"]["recommended_control_count"] == 7
    assert first["summary"]["open_question_count"] == 7
    assert first["security_context"]["detected_dependencies"][:3] == [
        "OAuth",
        "Postgres",
        "Salesforce",
    ]
    assert next(
        finding for finding in first["findings"] if finding["category"] == "dependency_exposure"
    )["severity"] == "high"


def test_generate_security_review_handles_sparse_specs_with_conservative_findings() -> None:
    review = generate_security_review(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-sec"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "evaluation": None,
        }
    )

    assert review["summary"]["title"] == "bu-sparse-sec"
    assert review["summary"]["workflow_context"] == "primary workflow"
    assert review["summary"]["stack"] == "unspecified"
    assert review["security_context"]["detected_dependencies"] == []
    assert review["security_context"]["mentions_authentication"] is False
    assert review["summary"]["high_or_critical_finding_count"] >= 4
    assert all(question["disposition"] == "blocks_security_signoff" for question in review["open_questions"])
    assert any(
        "does not name the authentication boundary" in finding["description"]
        for finding in review["findings"]
    )


def test_render_security_review_markdown_is_deterministic_and_traceable() -> None:
    review = generate_security_review(_rich_tact_spec())

    first = render_security_review_markdown(review)
    second = render_security_review_markdown(review)

    assert first == second
    assert first.startswith("# Renewal Risk Console Security Review")
    assert f"- Schema version: {SECURITY_REVIEW_SCHEMA_VERSION}" in first
    assert "## Findings" in first
    assert "## Recommended Controls" in first
    assert "## Open Questions" in first
    assert "### SEC-F5: External dependency exposure needs containment" in first
    assert "### SEC-C5: Constrain dependency trust boundaries" in first
    assert "Salesforce" in first
    assert "Slack" in first
    assert "OAuth" in first


def test_security_review_is_importable_from_spec_package() -> None:
    review = exported_generate(_rich_tact_spec())
    markdown = exported_render(review)

    assert review["schema_version"] == SECURITY_REVIEW_SCHEMA_VERSION
    assert markdown.startswith("# Renewal Risk Console Security Review")
