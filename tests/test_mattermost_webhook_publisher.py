"""Tests for Mattermost webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.mattermost_webhook import (
    MattermostWebhookPublishError,
    MattermostWebhookPublisher,
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
        "evidence": {"rationale": "Evidence supports the idea."},
        "quality": {"quality_score": 8.0},
        "evaluation": {"overall_score": 78.0, "recommendation": "yes"},
    }


def _design_brief_payload() -> dict:
    return {
        "source": {"entity_type": "design_brief", "id": "dbf-mm001"},
        "design_brief": {
            "id": "dbf-mm001",
            "title": "Mattermost Design Brief",
            "domain": "devtools",
            "theme": "review-handoff",
            "readiness_score": 86.0,
            "design_status": "draft",
            "lead_idea_id": "bu-mm001",
            "buyer": "Platform lead",
            "specific_user": "Agent reviewer",
            "workflow_context": "Design review",
            "source_idea_ids": ["bu-mm001", "bu-supporting"],
            "merged_product_concept": "Publish design briefs to Mattermost.",
            "why_this_now": "Reviewers work in Mattermost.",
            "mvp_scope": ["Render Markdown", "Record publication"],
            "validation_plan": "Dry run, then live publish.",
            "summary": "Publish design briefs to Mattermost.",
            "markdown": "# Mattermost Design Brief\n\nPublish design briefs to Mattermost.",
        },
    }


def test_dry_run_returns_mattermost_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MattermostWebhookPublisher(
        "https://chat.example.com/hooks/secret-token?debug=true",
        channel="town-square",
        username="Max Reviews",
        icon_url="https://example.com/max.png",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.url == "https://chat.example.com/hooks/[redacted]?[redacted]"
    assert "secret-token" not in result.url
    assert result.payload["channel"] == "town-square"
    assert result.payload["username"] == "Max Reviews"
    assert result.payload["icon_url"] == "https://example.com/max.png"
    assert result.payload["text"].startswith("### [Max] MCP Test Framework")
    assert "| Idea ID | bu-test001 |" in result.payload["text"]
    assert "**MVP Scope**" in result.payload["text"]
    assert result.payload["props"]["max"]["publisher"] == "max.mattermost_webhook"
    assert result.payload["props"]["max"]["idea_id"] == "bu-test001"


def test_design_brief_payload_renders_mattermost_markdown() -> None:
    publisher = MattermostWebhookPublisher("https://chat.example.com/hooks/secret-token")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.payload["text"].startswith("### [Max] Mattermost Design Brief")
    assert "| Brief ID | dbf-mm001 |" in result.payload["text"]
    assert "| Readiness | 86.0 |" in result.payload["text"]
    assert "**Rendered brief**" in result.payload["text"]
    assert result.payload["props"]["max"]["source_type"] == "design_brief"
    assert result.payload["props"]["max"]["design_brief_id"] == "dbf-mm001"
    assert result.payload["props"]["max"]["source_idea_ids"] == ["bu-mm001", "bu-supporting"]


def test_live_publish_posts_mattermost_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MattermostWebhookPublisher(
        "https://chat.example.com/hooks/secret-token",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.response_body == "ok"
    assert requests[0].url == "https://chat.example.com/hooks/secret-token"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["text"].startswith("### [Max] MCP Test Framework")
    assert posted["props"]["max"]["provider"] == "mattermost"


def test_live_publish_raises_for_mattermost_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="webhook failed")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MattermostWebhookPublisher(
        "https://chat.example.com/hooks/secret-token",
        client=client,
    )

    with pytest.raises(MattermostWebhookPublishError) as exc_info:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc_info.value.status_code == 500
    assert "webhook failed" in str(exc_info.value)


def test_from_env_reads_mattermost_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_MATTERMOST_WEBHOOK_URL", "https://chat.example.com/hooks/env-token")
    monkeypatch.setenv("MAX_MATTERMOST_CHANNEL", "product")
    monkeypatch.setenv("MAX_MATTERMOST_USERNAME", "Max Bot")
    monkeypatch.setenv("MAX_MATTERMOST_ICON_URL", "https://example.com/icon.png")

    publisher = MattermostWebhookPublisher.from_env()

    result = publisher.publish(_tact_spec(), dry_run=True)
    assert result.payload["channel"] == "product"
    assert result.payload["username"] == "Max Bot"
    assert result.payload["icon_url"] == "https://example.com/icon.png"


def test_from_env_requires_webhook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAX_MATTERMOST_WEBHOOK_URL", raising=False)

    with pytest.raises(MattermostWebhookPublishError, match="MAX_MATTERMOST_WEBHOOK_URL"):
        MattermostWebhookPublisher.from_env()
