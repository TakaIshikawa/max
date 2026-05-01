"""Tests for Webex webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.webex_webhook import (
    WebexWebhookPublishError,
    WebexWebhookPublisher,
    publish_webex_webhook,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-test001",
            "status": "approved",
            "domain": "devtools",
            "category": "cli_tool",
        },
        "project": {
            "title": "MCP Test Framework",
            "summary": "Standardized testing for MCP servers",
            "value_proposition": "Reduce regressions before release",
        },
        "problem": {"statement": "No standard way to test MCP servers"},
        "solution": {"approach": "A CLI tool that validates MCP server implementations"},
        "execution": {
            "mvp_scope": ["Protocol fixtures", "CLI runner"],
            "validation_plan": "Run with three teams.",
        },
        "evidence": {
            "rationale": "Evidence supports the idea.",
            "insight_ids": ["ins-test"],
            "signal_ids": ["sig-test"],
            "source_idea_ids": ["bu-source"],
        },
        "quality": {"quality_score": 8.0},
        "evaluation": {"overall_score": 78.0, "recommendation": "yes"},
    }


def _design_brief_payload() -> dict:
    return {
        "source": {"entity_type": "design_brief", "id": "dbf-webex001"},
        "design_brief": {
            "id": "dbf-webex001",
            "title": "Webex Design Brief",
            "domain": "devtools",
            "theme": "review-handoff",
            "readiness_score": 86.0,
            "design_status": "draft",
            "lead_idea_id": "bu-webex001",
            "source_idea_ids": ["bu-webex001", "bu-supporting"],
            "merged_product_concept": "Publish design briefs to Webex.",
            "why_this_now": "Reviewers work in Webex.",
            "mvp_scope": ["Render Markdown", "Record publication"],
            "validation_plan": "Dry run, then live publish.",
            "summary": "Publish design briefs to Webex.",
            "markdown": "# Webex Design Brief\n\nPublish design briefs to Webex.",
        },
        "evidence_refs": {
            "signal_ids": ["sig-webex", "sig-supporting"],
            "insight_ids": ["ins-webex"],
            "evidence_count": 3,
        },
    }


def test_dry_run_returns_webex_markdown_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = WebexWebhookPublisher(
        "https://webexapis.com/v1/webhooks/incoming/secret-token?debug=true",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.url == "https://webexapis.com/v1/webhooks/incoming/[redacted]?[redacted]"
    assert "secret-token" not in result.url
    assert result.payload["markdown"].startswith("### [Max] MCP Test Framework")
    assert "| Idea ID | bu-test001 |" in result.payload["markdown"]
    assert "| Recommendation | yes |" in result.payload["markdown"]
    assert "| Evidence count | 3 |" in result.payload["markdown"]
    assert "- Insights: ins-test" in result.payload["markdown"]
    assert "- Signals: sig-test" in result.payload["markdown"]
    assert "- Source ideas: bu-source" in result.payload["markdown"]
    assert result.payload["metadata"]["publisher"] == "max.webex_webhook"
    assert result.payload_preview.startswith("### [Max] MCP Test Framework")


def test_design_brief_payload_renders_webex_markdown() -> None:
    publisher = WebexWebhookPublisher("https://webexapis.com/v1/webhooks/incoming/secret-token")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.payload["markdown"].startswith("### [Max] Webex Design Brief")
    assert "| Brief ID | dbf-webex001 |" in result.payload["markdown"]
    assert "| Readiness | 86.0 |" in result.payload["markdown"]
    assert "| Evidence count | 3 |" in result.payload["markdown"]
    assert "- Insights: ins-webex" in result.payload["markdown"]
    assert "- Signals: sig-webex, sig-supporting" in result.payload["markdown"]
    assert "- Source ideas: bu-webex001, bu-supporting" in result.payload["markdown"]
    assert "**Rendered brief**" in result.payload["markdown"]
    assert result.payload["metadata"]["source_type"] == "design_brief"
    assert result.payload["metadata"]["design_brief_id"] == "dbf-webex001"


def test_live_publish_posts_webex_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok", headers={"x-webex-request-id": "req-123"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = WebexWebhookPublisher(
        "https://webexapis.com/v1/webhooks/incoming/secret-token",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.response_body == "ok"
    assert result.response_headers["x-webex-request-id"] == "req-123"
    assert requests[0].url == "https://webexapis.com/v1/webhooks/incoming/secret-token"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["markdown"].startswith("### [Max] MCP Test Framework")
    assert posted["metadata"]["provider"] == "webex"


def test_publish_webex_webhook_posts_with_helper() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, text="")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = publish_webex_webhook(
        _tact_spec(),
        webhook_url="https://webexapis.com/v1/webhooks/incoming/secret-token",
        dry_run=False,
        client=client,
    )

    assert result.status_code == 204
    assert json.loads(requests[0].read())["metadata"]["provider"] == "webex"


def test_live_publish_raises_for_webex_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"message":"Invalid webhook"}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = WebexWebhookPublisher(
        "https://webexapis.com/v1/webhooks/incoming/secret-token",
        client=client,
    )

    with pytest.raises(WebexWebhookPublishError) as exc_info:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc_info.value.status_code == 400
    assert "Invalid webhook" in str(exc_info.value)


def test_invalid_webhook_url_is_structured_failure() -> None:
    with pytest.raises(WebexWebhookPublishError, match="absolute http"):
        WebexWebhookPublisher("not-a-url")


def test_from_env_reads_webex_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAX_WEBEX_WEBHOOK_URL",
        "https://webexapis.com/v1/webhooks/incoming/env-token",
    )

    publisher = WebexWebhookPublisher.from_env()

    result = publisher.publish(_tact_spec(), dry_run=True)
    assert result.url == "https://webexapis.com/v1/webhooks/incoming/[redacted]"
    assert result.payload["metadata"]["provider"] == "webex"


def test_from_env_requires_webhook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAX_WEBEX_WEBHOOK_URL", raising=False)

    with pytest.raises(WebexWebhookPublishError, match="MAX_WEBEX_WEBHOOK_URL"):
        WebexWebhookPublisher.from_env()
