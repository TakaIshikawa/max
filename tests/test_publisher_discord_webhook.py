"""Tests for Discord webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.discord_webhook import DiscordWebhookPublishError, DiscordWebhookPublisher


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


def test_dry_run_returns_discord_embed_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = DiscordWebhookPublisher(
        "https://discord.com/api/webhooks/123/secret?wait=true",
        username="Max",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.url == "https://discord.com/api/webhooks/123/[redacted]?[redacted]"
    assert "secret" not in result.url
    assert result.payload["content"] == "[Max] MCP Test Framework"
    assert result.payload["username"] == "Max"
    embed = result.payload["embeds"][0]
    assert embed["title"] == "MCP Test Framework"
    assert embed["description"] == "Standardized testing for MCP servers"
    assert {"name": "Idea ID", "value": "bu-test001", "inline": True} in embed["fields"]
    assert {"name": "Problem", "value": "No standard way to test MCP servers", "inline": False} in embed["fields"]


def test_live_publish_posts_discord_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, text="")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = DiscordWebhookPublisher("https://discord.com/api/webhooks/123/secret", client=client)

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 204
    assert result.dry_run is False
    assert requests[0].url == "https://discord.com/api/webhooks/123/secret"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["embeds"][0]["title"] == "MCP Test Framework"


def test_live_publish_raises_for_discord_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"message":"Invalid Form Body"}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = DiscordWebhookPublisher("https://discord.com/api/webhooks/123/secret", client=client)

    with pytest.raises(DiscordWebhookPublishError) as exc_info:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc_info.value.status_code == 400
    assert "Invalid Form Body" in str(exc_info.value)


def test_build_payload_formats_design_brief() -> None:
    publisher = DiscordWebhookPublisher("https://discord.com/api/webhooks/123/secret")
    payload = publisher.build_payload(
        {
            "source": {"entity_type": "design_brief", "id": "dbf-test001"},
            "design_brief": {
                "id": "dbf-test001",
                "title": "Agent QA Brief",
                "domain": "devtools",
                "theme": "testing",
                "readiness_score": 82.0,
                "design_status": "approved",
                "lead_idea_id": "bu-test001",
                "merged_product_concept": "A validation workflow for agent tools.",
                "why_this_now": "Agent tooling is maturing.",
                "mvp_scope": ["Evidence matrix", "Validation CLI"],
                "validation_plan": "Run with two platform teams.",
                "source_idea_ids": ["bu-test001"],
            },
        }
    )

    embed = payload["embeds"][0]
    assert payload["content"] == "[Max] Agent QA Brief"
    assert embed["title"] == "Agent QA Brief"
    assert {"name": "Brief ID", "value": "dbf-test001", "inline": True} in embed["fields"]
    assert embed["footer"]["text"] == "max.discord_webhook | design_brief"
