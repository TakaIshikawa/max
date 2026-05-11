"""API tests for TactSpec rate limiting config generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.rate_limiting import RATE_LIMITING_SCHEMA_VERSION


def test_post_spec_rate_limiting_returns_generated_config() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/rate-limiting", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == RATE_LIMITING_SCHEMA_VERSION
    assert payload["kind"] == "max.rate_limiting_config"
    assert payload["source"]["idea_id"] == "bu-rate-limit-api"
    assert payload["summary"]["title"] == "Rate Limit Console"
    assert payload["summary"]["rate_limit_count"] >= 4
    assert {limit["type"] for limit in payload["rate_limits"]} >= {
        "api_endpoint_global",
        "authentication",
        "external_integration",
    }


def test_post_spec_rate_limiting_accepts_direct_spec_and_direct_idea_payloads() -> None:
    client = TestClient(create_app())

    spec_response = client.post("/api/v1/spec/rate-limiting", json=_tact_spec())
    idea_response = client.post("/api/v1/spec/rate-limiting", json=_idea())

    assert spec_response.status_code == 200
    assert idea_response.status_code == 200
    assert spec_response.json()["source"]["idea_id"] == "bu-rate-limit-api"
    assert idea_response.json()["summary"]["title"] == "Rate Limit Console"


def test_post_ideas_spec_rate_limiting_accepts_wrapped_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-rate-limiting", json={"idea": _idea()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["rate_limits"]


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-rate-limit-api", "status": "approved", "domain": "platform", "category": "application"},
        "project": {"title": "Rate Limit Console", "summary": "Protect API integrations.", "workflow_context": "public API access for webhook integrations"},
        "solution": {
            "technical_approach": "FastAPI service with OAuth authentication, Redis rate limiting, Stripe webhooks, Slack notifications, and mutation endpoints.",
            "composability_notes": "Expose webhooks for external integrations.",
        },
        "endpoints": [{"path": "/api/v1/accounts", "method": "GET"}, {"path": "/api/v1/accounts", "method": "POST"}],
        "integrations": [{"name": "Stripe", "purpose": "payments"}, {"name": "Slack", "purpose": "notifications"}],
        "security": {"auth": "OAuth 2.0 with JWT tokens"},
        "execution": {"mvp_scope": ["Authentication", "API access", "Mutation endpoint"]},
    }


def _idea() -> dict:
    return {
        "title": "Rate Limit Console",
        "one_liner": "Protect API integrations.",
        "category": "application",
        "problem": "Public API integrations need deterministic rate limits.",
        "solution": "Generate rate limiting guidance for a submitted idea.",
        "target_users": "platform teams",
        "value_proposition": "API policies are available before launch.",
        "workflow_context": "public API access for webhook integrations",
        "tech_approach": "FastAPI service with OAuth authentication, Redis rate limiting, Stripe webhooks, Slack notifications, and mutation endpoints.",
        "suggested_stack": {"backend": "FastAPI", "cache": "Redis", "auth": "OAuth"},
        "composability_notes": "Expose webhooks for external integrations.",
    }
