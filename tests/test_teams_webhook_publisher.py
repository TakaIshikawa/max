"""Tests for Microsoft Teams webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.teams_webhook import TeamsWebhookPublishError, TeamsWebhookPublisher


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
            "created_at": "2026-04-01T00:00:00",
            "updated_at": "2026-04-02T00:00:00",
        },
        "project": {
            "title": "MCP Test Framework",
            "summary": "Standardized testing for MCP servers",
            "value_proposition": "Reduce regressions before release",
        },
        "evidence": {
            "rationale": "Evidence supports the idea.",
            "insight_ids": ["ins-test001"],
            "signal_ids": ["sig-test001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {"quality_score": 8.0},
        "evaluation": {"overall_score": 78.0, "recommendation": "yes"},
    }


def test_dry_run_returns_teams_message_card_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TeamsWebhookPublisher(
        "https://example.webhook.office.com/webhookb2/token?sig=secret",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.url == "https://example.webhook.office.com/webhookb2/[redacted]?[redacted]"
    assert "secret" not in result.url
    assert result.payload["@type"] == "MessageCard"
    assert result.payload["@context"] == "https://schema.org/extensions"
    assert result.payload["title"] == "[Max] MCP Test Framework"
    assert result.payload["metadata"]["provider"] == "teams"
    assert result.payload["metadata"]["idea_id"] == "bu-test001"
    facts = result.payload["sections"][0]["facts"]
    assert {"name": "Idea ID", "value": "bu-test001"} in facts
    assert {"name": "Score", "value": "78.0"} in facts
    assert {"name": "Recommendation", "value": "yes"} in facts
    evidence_section = result.payload["sections"][2]
    assert evidence_section["title"] == "Evidence"
    assert {"name": "Signals", "value": "signals://sig-test001"} in evidence_section["facts"]


def test_title_override_and_include_evidence_false() -> None:
    publisher = TeamsWebhookPublisher("https://example.webhook.office.com/webhookb2/token")

    payload = publisher.build_payload(
        _tact_spec(),
        title="Custom Teams Title",
        include_evidence=False,
    )

    assert payload["title"] == "[Max] Custom Teams Title"
    assert payload["summary"] == "[Max] Custom Teams Title"
    assert [section.get("title") for section in payload["sections"]] == [None, "Metadata"]


def test_live_publish_posts_teams_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="1")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TeamsWebhookPublisher(
        "https://example.webhook.office.com/webhookb2/token",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.response_body == "1"
    assert requests[0].url == "https://example.webhook.office.com/webhookb2/token"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["@type"] == "MessageCard"
    assert posted["metadata"]["publisher"] == "max.teams_webhook"


def test_live_publish_raises_for_teams_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="workflow failed")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TeamsWebhookPublisher(
        "https://example.webhook.office.com/webhookb2/token",
        client=client,
    )

    with pytest.raises(TeamsWebhookPublishError) as exc_info:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc_info.value.status_code == 500
    assert "workflow failed" in str(exc_info.value)
