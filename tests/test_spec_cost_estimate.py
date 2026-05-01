from __future__ import annotations

from max.spec import generate_cost_estimate as exported_generate
from max.spec import render_cost_estimate_markdown as exported_render
from max.spec.cost_estimate import (
    COST_ESTIMATE_SCHEMA_VERSION,
    generate_cost_estimate,
    render_cost_estimate_markdown,
)


def _base_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-cost",
            "status": "approved",
            "domain": "developer-tools",
            "category": "cli_tool",
        },
        "project": {
            "title": "Release Note Summarizer",
            "summary": "Create local release notes from merged pull request titles.",
            "value_proposition": "Reduce manual release prep.",
            "target_users": "engineering teams",
            "specific_user": "release engineer",
            "buyer": "engineering manager",
            "workflow_context": "local release note generation",
        },
        "problem": {
            "statement": "Release owners manually combine merged PR titles.",
            "current_workaround": "Copy titles into a document.",
            "why_now": "Release cadence is increasing.",
        },
        "solution": {
            "approach": "Read a local changelog fixture and render markdown.",
            "technical_approach": "Python CLI with deterministic text grouping.",
            "suggested_stack": {"language": "python"},
        },
        "execution": {
            "mvp_scope": ["CLI command", "Markdown output"],
            "validation_plan": "Run against a local fixture.",
            "risks": [],
        },
        "quality": {
            "quality_score": 0.9,
            "novelty_score": 0.4,
            "usefulness_score": 0.8,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 76.0,
            "recommendation": "yes",
            "weaknesses": [],
            "dimensions": {
                "build_effort": {
                    "value": 3.0,
                    "confidence": 0.8,
                    "reasoning": "Small local CLI.",
                }
            },
        },
    }


def _medium_tact_spec() -> dict:
    spec = _base_tact_spec()
    spec["source"]["idea_id"] = "bu-medium-cost"
    spec["source"]["category"] = "application"
    spec["project"]["title"] = "Renewal Risk Slack Digest"
    spec["project"]["workflow_context"] = "Salesforce account review to Slack alert"
    spec["solution"] = {
        "approach": "Sync renewal risk fields and send Slack digests.",
        "technical_approach": "FastAPI webhook API with Salesforce API sync, Slack API messages, and Postgres storage.",
        "suggested_stack": {
            "backend": "FastAPI",
            "crm": "Salesforce",
            "messaging": "Slack",
            "database": "Postgres",
        },
    }
    spec["execution"] = {
        "mvp_scope": ["Salesforce sync", "Slack digest", "Pilot feedback review"],
        "first_10_customers": ["customer success pilot"],
        "validation_plan": "Run a customer pilot with sandbox API data.",
        "risks": ["Salesforce API limits may delay digest delivery."],
    }
    spec["evaluation"]["weaknesses"] = ["Integration reliability must be validated."]
    spec["evaluation"]["dimensions"]["build_effort"]["value"] = 6.0
    return spec


def _high_tact_spec() -> dict:
    spec = _medium_tact_spec()
    spec["source"]["idea_id"] = "bu-high-cost"
    spec["project"]["title"] = "AI Customer Health Command Center"
    spec["project"]["workflow_context"] = "real-time customer health workflow"
    spec["solution"] = {
        "approach": "Rank customer health, predict risk, and trigger billing and support workflows.",
        "technical_approach": (
            "Kubernetes service with OpenAI embeddings, vector search, Salesforce sync, "
            "Stripe billing data, Slack alerts, Datadog dashboards, OAuth SSO, and customer data retention controls."
        ),
        "suggested_stack": {
            "backend": "FastAPI",
            "ai": "OpenAI",
            "vector": "Pinecone",
            "crm": "Salesforce",
            "payments": "Stripe",
            "messaging": "Slack",
            "observability": "Datadog",
            "database": "Postgres",
        },
    }
    spec["execution"] = {
        "mvp_scope": [
            "Real-time Salesforce sync",
            "OpenAI embedding generation",
            "Vector search ranking",
            "Stripe expansion signal ingestion",
            "Slack escalation workflow",
            "Datadog operational dashboards",
        ],
        "first_10_customers": ["enterprise pilot", "CS pilot"],
        "validation_plan": "Run a high volume pilot with OAuth sandbox tenants and customer data fixtures.",
        "risks": [
            "OpenAI usage can exceed budget during embedding backfills.",
            "Customer data and PII require security review.",
            "Real-time sync failures can page on-call teams.",
        ],
    }
    spec["quality"]["quality_score"] = 0.4
    spec["quality"]["rejection_tags"] = ["expensive-integration-risk"]
    spec["evaluation"]["weaknesses"] = [
        "Security review is required.",
        "Operational ownership is unclear.",
    ]
    spec["evaluation"]["dimensions"]["build_effort"]["value"] = 9.0
    return spec


def test_generate_cost_estimate_is_deterministic_and_complete_for_medium_specs() -> None:
    first = generate_cost_estimate(_medium_tact_spec())
    second = generate_cost_estimate(_medium_tact_spec())

    assert first == second
    assert first["schema_version"] == COST_ESTIMATE_SCHEMA_VERSION
    assert first["kind"] == "max.cost_estimate"
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "cost_drivers",
        "effort_estimate",
        "risks",
        "recommendations",
    }
    assert first["source"]["idea_id"] == "bu-medium-cost"
    assert first["summary"]["title"] == "Renewal Risk Slack Digest"
    assert first["summary"]["effort_band"] == "medium"
    assert first["effort_estimate"]["band"] == "medium"
    assert {driver["category"] for driver in first["cost_drivers"]} == {
        "external_service",
        "operational",
    }
    assert any(driver["name"] == "crm" for driver in first["cost_drivers"])
    assert any(driver["name"] == "messaging" for driver in first["cost_drivers"])
    assert any(risk["name"] == "validation_rework" for risk in first["risks"])


def test_generate_cost_estimate_covers_low_medium_and_high_complexity_bands() -> None:
    low = generate_cost_estimate(_base_tact_spec())
    medium = generate_cost_estimate(_medium_tact_spec())
    high = generate_cost_estimate(_high_tact_spec())

    assert low["effort_estimate"]["band"] == "low"
    assert low["effort_estimate"]["engineering_days"] == "2-5"
    assert medium["effort_estimate"]["band"] == "medium"
    assert medium["effort_estimate"]["engineering_days"] == "6-15"
    assert high["effort_estimate"]["band"] == "high"
    assert high["effort_estimate"]["engineering_days"] == "16-30"
    assert any(driver["impact"] == "high" for driver in high["cost_drivers"])
    assert any(risk["severity"] == "high" for risk in high["risks"])
    assert any(
        recommendation["id"] == "REC3" for recommendation in high["recommendations"]
    )


def test_generate_cost_estimate_handles_missing_optional_fields() -> None:
    estimate = generate_cost_estimate(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-cost"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "quality": {},
            "evaluation": None,
        }
    )

    assert estimate["summary"]["title"] == "bu-sparse-cost"
    assert estimate["summary"]["workflow_context"] == "primary workflow"
    assert estimate["summary"]["stack"] == "unspecified"
    assert estimate["summary"]["effort_band"] == "low"
    assert estimate["cost_drivers"] == []
    assert estimate["effort_estimate"]["basis"] == [
        "0 MVP scope item(s)",
        "0 stack component(s)",
        "0 external service cost category/categories",
        "0 execution risk(s)",
        "0 evaluation weakness(es)",
    ]
    assert any(item["id"] == "REC5" for item in estimate["recommendations"])


def test_render_cost_estimate_markdown_is_readable_and_deterministic() -> None:
    estimate = generate_cost_estimate(_high_tact_spec())

    first = render_cost_estimate_markdown(estimate)
    second = render_cost_estimate_markdown(estimate)

    assert first == second
    assert first.startswith("# AI Customer Health Command Center Cost Estimate")
    assert f"- Schema version: {COST_ESTIMATE_SCHEMA_VERSION}" in first
    assert "- Effort band: high" in first
    assert "## Effort Estimate" in first
    assert "## Cost Drivers" in first
    assert "## Risks" in first
    assert "## Recommendations" in first
    assert "### CR2: usage_based_spend" in first
    assert "### CR3: security_and_privacy_review" in first
    assert "- Mitigation:" in first
    assert "OpenAI" in first


def test_cost_estimate_is_importable_from_spec_package() -> None:
    estimate = exported_generate(_base_tact_spec())
    markdown = exported_render(estimate)

    assert estimate["schema_version"] == COST_ESTIMATE_SCHEMA_VERSION
    assert markdown.startswith("# Release Note Summarizer Cost Estimate")
