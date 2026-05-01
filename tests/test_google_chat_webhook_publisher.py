"""Tests for Google Chat webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.google_chat_webhook import (
    GoogleChatWebhookPublishError,
    GoogleChatWebhookPublisher,
    publish_google_chat_webhook,
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
        "source": {"entity_type": "design_brief", "id": "dbf-gchat001"},
        "design_brief": {
            "id": "dbf-gchat001",
            "title": "Google Chat Design Brief",
            "domain": "devtools",
            "theme": "review-handoff",
            "readiness_score": 86.0,
            "design_status": "draft",
            "lead_idea_id": "bu-gchat001",
            "source_idea_ids": ["bu-gchat001", "bu-supporting"],
            "merged_product_concept": "Publish design briefs to Google Chat.",
            "why_this_now": "Reviewers work in Google Chat.",
            "mvp_scope": ["Render cards", "Record publication"],
            "validation_plan": "Dry run, then live publish.",
            "summary": "Publish design briefs to Google Chat.",
            "recommendation": "ship",
        },
        "evidence_refs": {
            "signal_ids": ["sig-gchat", "sig-supporting"],
            "insight_ids": ["ins-gchat"],
            "evidence_count": 3,
        },
    }


def test_dry_run_returns_google_chat_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleChatWebhookPublisher(
        "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=secret&token=token",
        thread_key="release-review",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.url == "https://chat.googleapis.com/v1/spaces/AAAA/[redacted]?[redacted]"
    assert "secret" not in result.url
    assert result.payload["text"].startswith("[Max] MCP Test Framework")
    assert "Recommendation: yes" in result.payload["text"]
    assert "Validation: Run with three teams." in result.payload["text"]
    assert "Evidence count: 3" in result.payload["text"]
    assert result.payload["metadata"]["publisher"] == "max.google_chat_webhook"
    assert result.payload["metadata"]["idea_id"] == "bu-test001"
    assert result.payload_preview.startswith("[Max] MCP Test Framework")
    card = result.payload["cardsV2"][0]["card"]
    widgets = card["sections"][0]["widgets"]
    assert card["header"]["title"] == "MCP Test Framework"
    assert {"decoratedText": {"topLabel": "Idea ID", "text": "bu-test001"}} in widgets
    assert {"decoratedText": {"topLabel": "Recommendation", "text": "yes"}} in widgets
    assert "Insights: ins-test" in card["sections"][2]["widgets"][0]["textParagraph"]["text"]


def test_design_brief_payload_renders_google_chat_card() -> None:
    publisher = GoogleChatWebhookPublisher(
        "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=secret&token=token"
    )

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.payload["text"].startswith("[Max] Google Chat Design Brief")
    assert "Recommendation: ship" in result.payload["text"]
    assert "Evidence count: 3" in result.payload["text"]
    assert result.payload["metadata"]["source_type"] == "design_brief"
    assert result.payload["metadata"]["design_brief_id"] == "dbf-gchat001"
    assert result.payload["metadata"]["source_idea_ids"] == ["bu-gchat001", "bu-supporting"]
    card = result.payload["cardsV2"][0]["card"]
    assert card["header"]["subtitle"] == "devtools"
    assert {"decoratedText": {"topLabel": "Brief ID", "text": "dbf-gchat001"}} in card[
        "sections"
    ][0]["widgets"]
    assert "Signals: sig-gchat, sig-supporting" in card["sections"][2]["widgets"][0][
        "textParagraph"
    ]["text"]


def test_live_publish_posts_google_chat_payload_with_thread_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text='{"name":"spaces/AAAA/messages/123"}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleChatWebhookPublisher(
        "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=secret&token=token",
        thread_key="release-review",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.response_body == '{"name":"spaces/AAAA/messages/123"}'
    assert requests[0].url.params["key"] == "secret"
    assert requests[0].url.params["token"] == "token"
    assert requests[0].url.params["threadKey"] == "release-review"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["text"].startswith("[Max] MCP Test Framework")
    assert posted["cardsV2"][0]["cardId"] == "idea"
    assert posted["metadata"]["provider"] == "google_chat"


def test_publish_google_chat_webhook_posts_with_helper() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, text="")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = publish_google_chat_webhook(
        _tact_spec(),
        webhook_url="https://chat.googleapis.com/v1/spaces/AAAA/messages?key=secret&token=token",
        thread_key="helper-thread",
        dry_run=False,
        client=client,
    )

    assert result.status_code == 204
    assert requests[0].url.params["threadKey"] == "helper-thread"
    assert json.loads(requests[0].read())["metadata"]["provider"] == "google_chat"


def test_live_publish_raises_for_google_chat_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text='{"error":{"message":"Permission denied"}}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleChatWebhookPublisher(
        "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=secret&token=token",
        client=client,
    )

    with pytest.raises(GoogleChatWebhookPublishError) as exc_info:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc_info.value.status_code == 403
    assert "Permission denied" in str(exc_info.value)


def test_invalid_webhook_url_is_structured_failure() -> None:
    with pytest.raises(GoogleChatWebhookPublishError, match="absolute http"):
        GoogleChatWebhookPublisher("not-a-url")


def test_from_env_reads_google_chat_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GOOGLE_CHAT_WEBHOOK_URL",
        "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=env&token=env-token",
    )
    monkeypatch.setenv("GOOGLE_CHAT_THREAD_KEY", "env-thread")

    publisher = GoogleChatWebhookPublisher.from_env(timeout=3.5)

    assert publisher.thread_key == "env-thread"
    assert publisher.timeout == 3.5
    result = publisher.publish(_tact_spec(), dry_run=True)
    assert result.url == "https://chat.googleapis.com/v1/spaces/AAAA/[redacted]?[redacted]"
    assert result.payload["metadata"]["provider"] == "google_chat"


def test_from_env_requires_webhook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)

    with pytest.raises(GoogleChatWebhookPublishError, match="GOOGLE_CHAT_WEBHOOK_URL"):
        GoogleChatWebhookPublisher.from_env()
