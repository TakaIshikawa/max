from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_security_review as exported_generate
from max.spec import render_security_review_csv as exported_render_csv
from max.spec import render_security_review_markdown as exported_render
from max.spec.security_review import (
    SECURITY_REVIEW_CSV_COLUMNS,
    SECURITY_REVIEW_SCHEMA_VERSION,
    generate_security_review,
    render_security_review_csv,
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


def test_render_security_review_csv_has_stable_header_and_traceable_rows() -> None:
    review = generate_security_review(_rich_tact_spec())

    first = render_security_review_csv(review)
    second = render_security_review_csv(review)
    rows = list(csv.DictReader(StringIO(first)))

    assert first == second
    assert first.endswith("\n")
    assert first.splitlines()[0] == ",".join(SECURITY_REVIEW_CSV_COLUMNS)
    assert rows[0] == {
        "section": "summary",
        "type": "summary",
        "source_idea_id": "bu-sec",
        "source_status": "approved",
        "source_domain": "customer-success",
        "source_category": "application",
        "tact_spec_schema_version": "tact-spec-preview/v1",
        "title": "Renewal Risk Console",
        "workflow_context": "Salesforce account review to Slack renewal alert",
        "target_user": "customer success operator",
        "buyer": "customer success director",
        "stack": "auth=OAuth, backend=FastAPI, crm=Salesforce, database=Postgres, messaging=Slack",
        "recommendation": "yes",
        "overall_score": "88.0",
        "finding_count": "7",
        "high_or_critical_finding_count": "1",
        "recommended_control_count": "7",
        "open_question_count": "7",
        "context_detected_dependencies": "OAuth; Postgres; Salesforce; Slack; Webhook; FastAPI",
        "context_mentions_authentication": "true",
        "context_mentions_authorization": "true",
        "context_mentions_secret_handling": "true",
        "context_mentions_data_retention": "true",
        "context_mentions_audit_logging": "true",
        "context_mentions_abuse_cases": "true",
        "item_id": "summary",
        "name": "",
        "category": "",
        "category_title": "",
        "severity": "",
        "status": "yes",
        "owner": "",
        "description": "Salesforce account review to Slack renewal alert",
        "recommendation_text": "",
        "evidence": "",
        "derived_from": "",
        "related_controls": "",
        "related_questions": "",
        "disposition": "",
        "question": "",
    }
    assert reader_fieldnames(first) == list(SECURITY_REVIEW_CSV_COLUMNS)
    assert [row["section"] for row in rows].count("findings") == 7
    assert [row["section"] for row in rows].count("recommended_controls") == 7
    assert [row["section"] for row in rows].count("open_questions") == 7

    dependency_finding = next(row for row in rows if row["item_id"] == "SEC-F5")
    assert dependency_finding["section"] == "findings"
    assert dependency_finding["category"] == "dependency_exposure"
    assert dependency_finding["severity"] == "high"
    assert dependency_finding["evidence"] == "OAuth; Postgres; Salesforce; Slack; Webhook; FastAPI"
    assert dependency_finding["related_controls"] == "SEC-C5"
    assert dependency_finding["related_questions"] == "SEC-Q5"

    dependency_control = next(row for row in rows if row["item_id"] == "SEC-C5")
    assert dependency_control["section"] == "recommended_controls"
    assert dependency_control["owner"] == "integration_owner"
    assert dependency_control["related_questions"] == "SEC-Q5"
    assert "OAuth scopes" in dependency_control["recommendation_text"]

    dependency_question = next(row for row in rows if row["item_id"] == "SEC-Q5")
    assert dependency_question["section"] == "open_questions"
    assert dependency_question["related_controls"] == "SEC-C5"
    assert dependency_question["disposition"] == "needs_confirmation"


def test_render_security_review_csv_handles_sparse_reviews_with_readable_booleans() -> None:
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

    csv_text = render_security_review_csv(review)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_security_review_csv(review)
    assert rows[0]["title"] == "bu-sparse-sec"
    assert rows[0]["workflow_context"] == "primary workflow"
    assert rows[0]["stack"] == "unspecified"
    assert rows[0]["context_detected_dependencies"] == ""
    assert rows[0]["context_mentions_authentication"] == "false"
    assert rows[0]["context_mentions_authorization"] == "false"
    assert rows[0]["context_mentions_secret_handling"] == "false"
    assert next(row for row in rows if row["item_id"] == "SEC-F1")["severity"] == "high"
    assert all(
        row["disposition"] == "blocks_security_signoff"
        for row in rows
        if row["section"] == "open_questions"
    )


def test_render_security_review_csv_preserves_high_risk_terms() -> None:
    review = generate_security_review(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-high-risk-sec", "status": "approved"},
            "project": {
                "title": "Credential Export Gateway",
                "specific_user": "support admin",
                "workflow_context": "PII export into Slack and Stripe workflows",
            },
            "solution": {
                "technical_approach": (
                    "OAuth OIDC JWT login with SSO, API key rotation, webhook signing, "
                    "tenant RBAC, audit log events, prompt injection checks, DoS rate limits, "
                    "and encrypted retention deletion."
                ),
                "suggested_stack": {"payments": "Stripe", "messaging": "Slack"},
            },
            "execution": {
                "risks": ["Credential exfiltration from personal data exports."],
            },
            "evaluation": {"overall_score": 91, "recommendation": "yes"},
        }
    )

    rows = list(csv.DictReader(StringIO(render_security_review_csv(review))))

    summary = rows[0]
    assert summary["context_mentions_authentication"] == "true"
    assert summary["context_mentions_authorization"] == "true"
    assert summary["context_mentions_secret_handling"] == "true"
    assert summary["context_mentions_data_retention"] == "true"
    assert summary["context_mentions_audit_logging"] == "true"
    assert summary["context_mentions_abuse_cases"] == "true"
    assert "Stripe" in summary["context_detected_dependencies"]
    assert "Slack" in summary["context_detected_dependencies"]
    assert next(row for row in rows if row["item_id"] == "SEC-F3")["evidence"] == (
        "API key; credential; webhook"
    )


def test_render_security_review_csv_escapes_commas_and_newlines() -> None:
    review = generate_security_review(_rich_tact_spec())
    review["findings"][0]["description"] = 'Review "quoted", comma value\nbefore release.'
    review["recommended_controls"][0]["recommendation"] = "Store token,\nrotate token."
    review["open_questions"][0]["question"] = "Who approves, logs,\nand deletes?"

    csv_text = render_security_review_csv(review)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Review ""quoted"", comma value\nbefore release."' in csv_text
    assert '"Store token,\nrotate token."' in csv_text
    assert rows[1]["description"] == 'Review "quoted", comma value\nbefore release.'
    assert next(row for row in rows if row["item_id"] == "SEC-C1")["recommendation_text"] == (
        "Store token,\nrotate token."
    )
    assert next(row for row in rows if row["item_id"] == "SEC-Q1")["question"] == (
        "Who approves, logs,\nand deletes?"
    )


def test_security_review_is_importable_from_spec_package() -> None:
    review = exported_generate(_rich_tact_spec())
    markdown = exported_render(review)
    csv_text = exported_render_csv(review)

    assert review["schema_version"] == SECURITY_REVIEW_SCHEMA_VERSION
    assert markdown.startswith("# Renewal Risk Console Security Review")
    assert csv_text.startswith(",".join(SECURITY_REVIEW_CSV_COLUMNS))


def reader_fieldnames(csv_text: str) -> list[str] | None:
    return csv.DictReader(StringIO(csv_text)).fieldnames
