"""Tests for Slack webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.slack_webhook import SlackWebhookPublishError, SlackWebhookPublisher


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


def test_dry_run_returns_slack_block_kit_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SlackWebhookPublisher(
        "https://hooks.slack.com/services/T000/B000/secret",
        channel="#ideas",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.payload["text"] == "[Max] MCP Test Framework"
    assert result.payload["channel"] == "#ideas"
    assert result.payload["blocks"][0]["type"] == "header"
    assert result.payload["blocks"][1]["type"] == "section"
    assert result.payload["metadata"]["event_payload"]["idea_id"] == "bu-test001"


def test_live_publish_posts_slack_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SlackWebhookPublisher("https://hooks.slack.com/services/T000/B000/secret", client=client)

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.response_body == "ok"
    assert requests[0].url == "https://hooks.slack.com/services/T000/B000/secret"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["text"] == "[Max] MCP Test Framework"
    assert "blocks" in posted


def test_live_publish_raises_for_slack_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid_payload")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SlackWebhookPublisher("https://hooks.slack.com/services/T000/B000/secret", client=client)

    with pytest.raises(SlackWebhookPublishError) as exc_info:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc_info.value.status_code == 400
    assert "invalid_payload" in str(exc_info.value)


def test_live_publish_retries_transient_slack_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, text="rate_limited", headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True, "channel": "C123", "ts": "1710000000.000100"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SlackWebhookPublisher(
        "https://hooks.slack.com/services/T000/B000/secret",
        client=client,
        max_retries=1,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.ok is True
    assert result.channel == "C123"
    assert result.ts == "1710000000.000100"
    assert result.attempts == 2
    assert result.to_dict() == {"ok": True, "channel": "C123", "ts": "1710000000.000100"}
    assert len(requests) == 2


def test_missing_webhook_url_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Slack webhook URL is required"):
        SlackWebhookPublisher("")


def test_build_payload_formats_design_brief() -> None:
    publisher = SlackWebhookPublisher(
        "https://hooks.slack.com/services/T000/B000/secret",
        username="Max Reviews",
        icon_emoji=":memo:",
    )
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
                "buyer": "Platform lead",
                "specific_user": "Agent reviewer",
                "workflow_context": "Design review",
                "merged_product_concept": "A validation workflow for agent tools.",
                "why_this_now": "Agent tooling is maturing.",
                "mvp_scope": ["Evidence matrix", "Validation CLI"],
                "validation_plan": "Run with two platform teams.",
                "source_idea_ids": ["bu-test001"],
            },
        }
    )

    assert payload["text"] == "[Max] Agent QA Brief"
    assert payload["username"] == "Max Reviews"
    assert payload["icon_emoji"] == ":memo:"
    assert payload["metadata"]["event_payload"]["source_type"] == "design_brief"
    assert payload["metadata"]["event_payload"]["design_brief_id"] == "dbf-test001"
    assert payload["metadata"]["event_payload"]["readiness_score"] == 82.0
    assert payload["metadata"]["event_payload"]["source_idea_ids"] == ["bu-test001"]
    assert payload["blocks"][2]["fields"][6]["text"] == "*Buyer*\nPlatform lead"
    assert payload["blocks"][2]["fields"][7]["text"] == "*User*\nAgent reviewer"
    assert payload["blocks"][2]["fields"][8]["text"] == "*Workflow*\nDesign review"
