from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_cost_estimate as exported_generate
from max.spec import render_cost_estimate_csv as exported_render_csv
from max.spec import render_cost_estimate_markdown as exported_render
from max.spec.cost_estimate import (
    COST_ESTIMATE_CSV_COLUMNS,
    COST_ESTIMATE_SCHEMA_VERSION,
    generate_cost_estimate,
    render_cost_estimate_csv,
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
    csv_text = exported_render_csv(estimate)

    assert estimate["schema_version"] == COST_ESTIMATE_SCHEMA_VERSION
    assert markdown.startswith("# Release Note Summarizer Cost Estimate")
    assert csv_text.startswith("schema_version,kind,source_idea_id,title,")


def test_render_cost_estimate_csv_for_generated_estimate_is_parseable_and_deterministic() -> None:
    estimate = generate_cost_estimate(_medium_tact_spec())

    first = render_cost_estimate_csv(estimate)
    second = render_cost_estimate_csv(estimate)
    reader = csv.DictReader(StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(COST_ESTIMATE_CSV_COLUMNS)
    assert [row["item"] for row in rows] == [
        driver["name"] for driver in estimate["cost_drivers"]
    ]
    assert {row["category"] for row in rows} == {"external_service", "operational"}
    assert all(row["schema_version"] == COST_ESTIMATE_SCHEMA_VERSION for row in rows)
    assert all(row["kind"] == "max.cost_estimate" for row in rows)
    assert all(row["source_idea_id"] == "bu-medium-cost" for row in rows)
    assert all(row["title"] == "Renewal Risk Slack Digest" for row in rows)
    assert all(row["estimate_type"] == "driver" for row in rows)
    assert all(row["confidence"] == "medium" for row in rows)


def test_render_cost_estimate_csv_flattens_multiple_cost_line_items() -> None:
    estimate = {
        "schema_version": COST_ESTIMATE_SCHEMA_VERSION,
        "kind": "max.cost_estimate",
        "source": {"idea_id": "bu-budget"},
        "summary": {"title": "Budget Planner"},
        "cost_line_items": [
            {
                "category": "external_service",
                "item": "OpenAI embeddings",
                "description": "Embedding generation for pilot records.",
                "estimate_type": "usage_based",
                "monthly_cost": {"low": 25, "base": 75, "high": 150},
                "one_time_cost": 0,
                "assumptions": ["10k records", "pilot traffic"],
                "confidence": "medium",
                "notes": "review after first import",
            },
            {
                "category": "implementation",
                "item": "Security review",
                "description": "Review data handling before launch.",
                "estimate_type": "one_time",
                "base_monthly_cost": 0,
                "one_time_cost": 1200,
                "assumptions": ["standard review"],
                "confidence": "high",
            },
        ],
    }

    rows = list(csv.DictReader(StringIO(render_cost_estimate_csv(estimate))))

    assert [row["item"] for row in rows] == ["OpenAI embeddings", "Security review"]
    assert rows[0]["low_monthly_cost"] == "25"
    assert rows[0]["base_monthly_cost"] == "75"
    assert rows[0]["high_monthly_cost"] == "150"
    assert rows[0]["one_time_cost"] == "0"
    assert rows[0]["assumptions"] == "10k records | pilot traffic"
    assert rows[0]["notes"] == "review after first import"
    assert rows[1]["base_monthly_cost"] == "0"
    assert rows[1]["one_time_cost"] == "1200"
    assert rows[1]["notes"] == ""


def test_render_cost_estimate_csv_preserves_numeric_values_as_cells() -> None:
    estimate = {
        "schema_version": COST_ESTIMATE_SCHEMA_VERSION,
        "kind": "max.cost_estimate",
        "cost_line_items": [
            {
                "category": "cloud",
                "item": "Postgres",
                "estimate_type": "subscription",
                "low_monthly_cost": 19.99,
                "monthly_cost": 49.5,
                "high_monthly_cost": 99,
                "one_time_cost": 250,
            }
        ],
    }

    row = next(csv.DictReader(StringIO(render_cost_estimate_csv(estimate))))

    assert row["low_monthly_cost"] == "19.99"
    assert row["base_monthly_cost"] == "49.5"
    assert row["high_monthly_cost"] == "99"
    assert row["one_time_cost"] == "250"


def test_render_cost_estimate_csv_escapes_commas_quotes_and_newlines() -> None:
    estimate = {
        "schema_version": COST_ESTIMATE_SCHEMA_VERSION,
        "kind": "max.cost_estimate",
        "summary": {"title": "Escaping, Budget"},
        "cost_line_items": [
            {
                "category": "external,service",
                "item": 'API "usage"',
                "description": "Line one\nLine two, with comma",
                "estimate_type": "usage_based",
                "monthly_cost": {"base": 88},
                "notes": 'vendor says "review"',
            }
        ],
    }

    csv_text = render_cost_estimate_csv(estimate)
    row = next(csv.DictReader(StringIO(csv_text)))

    assert '"Escaping, Budget"' in csv_text
    assert row["category"] == "external,service"
    assert row["item"] == 'API "usage"'
    assert row["description"] == "Line one Line two, with comma"
    assert row["notes"] == 'vendor says "review"'


def test_render_cost_estimate_csv_handles_minimal_estimates() -> None:
    csv_text = render_cost_estimate_csv({})
    reader = csv.DictReader(StringIO(csv_text))

    assert csv_text.endswith("\n")
    assert reader.fieldnames == list(COST_ESTIMATE_CSV_COLUMNS)
    assert list(reader) == []
