"""API tests for TactSpec data classification generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.data_classification import DATA_CLASSIFICATION_SCHEMA_VERSION


def test_post_spec_data_classification_returns_structured_data_and_markdown() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/data-classification", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == DATA_CLASSIFICATION_SCHEMA_VERSION
    assert payload["kind"] == "max.spec.data_classification"
    assert payload["source"]["idea_id"] == "bu-data-class-api"
    assert payload["summary"]["title"] == "Customer Data Classifier"
    assert payload["data_categories"]
    assert payload["sensitivity"]["level"] in {"restricted", "confidential", "internal"}
    assert payload["markdown"].startswith("# Customer Data Classifier Data Classification")


def test_post_spec_data_classification_accepts_direct_spec_and_direct_idea_payloads() -> None:
    client = TestClient(create_app())

    spec_response = client.post("/api/v1/spec/data-classification", json=_tact_spec())
    idea_response = client.post("/api/v1/spec/data-classification", json=_idea())

    assert spec_response.status_code == 200
    assert idea_response.status_code == 200
    assert spec_response.json()["source"]["idea_id"] == "bu-data-class-api"
    assert idea_response.json()["summary"]["title"] == "Customer Data Classifier"


def test_post_ideas_spec_data_classification_uses_same_generator_path() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-data-classification", json={"idea": _idea()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["transfer_touchpoints"]
    assert "## Data Categories" in payload["markdown"]


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-data-class-api", "status": "approved", "domain": "finance", "category": "application"},
        "project": {
            "title": "Customer Data Classifier",
            "summary": "Classify customer account records before Slack escalation.",
            "target_users": "support teams",
            "specific_user": "support operator",
            "workflow_context": "customer account review with email and payment notes",
        },
        "solution": {
            "technical_approach": "FastAPI app stores customer emails, invoices, OAuth tokens, audit logs, OpenAI prompts, and Slack webhook payloads in Postgres.",
            "suggested_stack": {"backend": "FastAPI", "database": "Postgres", "messaging": "Slack", "ai": "OpenAI"},
        },
        "execution": {"risks": ["Payment notes and customer emails require careful handling."]},
    }


def _idea() -> dict:
    return {
        "title": "Customer Data Classifier",
        "one_liner": "Classify customer data before sharing workflow records.",
        "category": "application",
        "problem": "Support teams mix customer emails, payment notes, and Slack messages.",
        "solution": "Generate classification guidance from the submitted idea.",
        "target_users": "support teams",
        "value_proposition": "Data handling requirements are visible before launch.",
        "specific_user": "support operator",
        "workflow_context": "customer account review with email and payment notes",
        "tech_approach": "FastAPI app stores customer emails, invoices, OAuth tokens, audit logs, OpenAI prompts, and Slack webhook payloads in Postgres.",
        "suggested_stack": {"backend": "FastAPI", "database": "Postgres", "messaging": "Slack", "ai": "OpenAI"},
    }
