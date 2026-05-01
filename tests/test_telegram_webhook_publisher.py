"""Tests for Telegram webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.telegram_webhook import (
    TelegramWebhookPublishError,
    TelegramWebhookPublisher,
    publish_telegram_webhook,
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
        "source": {"entity_type": "design_brief", "id": "dbf-telegram001"},
        "design_brief": {
            "id": "dbf-telegram001",
            "title": "Telegram Design Brief",
            "domain": "devtools",
            "theme": "review-handoff",
            "readiness_score": 86.0,
            "design_status": "draft",
            "lead_idea_id": "bu-telegram001",
            "source_idea_ids": ["bu-telegram001", "bu-supporting"],
            "merged_product_concept": "Publish design briefs to Telegram.",
            "why_this_now": "Reviewers work in Telegram.",
            "mvp_scope": ["Render text", "Record publication"],
            "validation_plan": "Dry run, then live publish.",
            "summary": "Publish design briefs to Telegram.",
            "recommendation": "ship",
            "markdown": "# Telegram Design Brief\n\nPublish design briefs to Telegram.",
        },
        "evidence_refs": {
            "signal_ids": ["sig-telegram", "sig-supporting"],
            "insight_ids": ["ins-telegram"],
            "evidence_count": 3,
        },
    }


def test_dry_run_returns_telegram_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TelegramWebhookPublisher(
        "12345",
        token="123456:secret-token",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.url == "https://api.telegram.org/bot[redacted]/sendMessage"
    assert "secret-token" not in result.url
    assert result.payload == {
        "chat_id": "12345",
        "text": (
            "[Max] MCP Test Framework\n"
            "\n"
            "Standardized testing for MCP servers\n"
            "\n"
            "Idea ID: bu-test001\n"
            "Status: approved\n"
            "Domain: devtools\n"
            "Category: cli_tool\n"
            "Score: 78.0\n"
            "Recommendation: yes\n"
            "Quality: 8.0\n"
            "Evidence count: 3\n"
            "\n"
            "Problem: No standard way to test MCP servers\n"
            "\n"
            "Solution: A CLI tool that validates MCP server implementations\n"
            "\n"
            "MVP Scope:\n"
            "- Protocol fixtures\n"
            "- CLI runner\n"
            "\n"
            "Validation: Run with three teams.\n"
            "\n"
            "Evidence: Evidence supports the idea.\n"
            "\n"
            "Source identifiers:\n"
            "- Insights: ins-test\n"
            "- Signals: sig-test\n"
            "- Source ideas: bu-source"
        ),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "metadata": {
            "publisher": "max.telegram_webhook",
            "provider": "telegram",
            "source_type": "idea",
            "idea_id": "bu-test001",
            "status": "approved",
            "domain": "devtools",
            "category": "cli_tool",
            "evidence_count": 3,
            "insight_ids": ["ins-test"],
            "signal_ids": ["sig-test"],
            "source_idea_ids": ["bu-source"],
        },
    }
    assert result.payload_preview.startswith("[Max] MCP Test Framework")


def test_design_brief_payload_renders_telegram_message() -> None:
    publisher = TelegramWebhookPublisher("12345", token="123456:secret-token")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.payload["text"].startswith("[Max] Telegram Design Brief")
    assert "Brief ID: dbf-telegram001" in result.payload["text"]
    assert "Readiness: 86.0" in result.payload["text"]
    assert "Recommendation: ship" in result.payload["text"]
    assert "- Signals: sig-telegram, sig-supporting" in result.payload["text"]
    assert "Rendered brief:" in result.payload["text"]
    assert result.payload["metadata"]["source_type"] == "design_brief"
    assert result.payload["metadata"]["design_brief_id"] == "dbf-telegram001"
    assert result.payload["metadata"]["source_idea_ids"] == [
        "bu-telegram001",
        "bu-supporting",
    ]


def test_live_publish_posts_telegram_payload_to_send_message() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text='{"ok":true,"result":{"message_id":42}}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TelegramWebhookPublisher(
        "12345",
        token="123456:secret-token",
        disable_web_page_preview=False,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.response_body == '{"ok":true,"result":{"message_id":42}}'
    assert requests[0].url == "https://api.telegram.org/bot123456:secret-token/sendMessage"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["chat_id"] == "12345"
    assert posted["text"].startswith("[Max] MCP Test Framework")
    assert posted["disable_web_page_preview"] is False
    assert posted["metadata"]["provider"] == "telegram"


def test_publish_telegram_webhook_posts_with_helper() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, text="")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = publish_telegram_webhook(
        _tact_spec(),
        chat_id="12345",
        token="123456:secret-token",
        dry_run=False,
        client=client,
    )

    assert result.status_code == 204
    assert json.loads(requests[0].read())["metadata"]["provider"] == "telegram"


def test_live_publish_raises_for_telegram_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"ok":false,"description":"Bad Request"}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TelegramWebhookPublisher(
        "12345",
        token="123456:secret-token",
        client=client,
    )

    with pytest.raises(TelegramWebhookPublishError) as exc_info:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc_info.value.status_code == 400
    assert "Bad Request" in str(exc_info.value)


def test_constructor_reads_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")

    publisher = TelegramWebhookPublisher("12345", parse_mode="HTML")

    result = publisher.publish(_tact_spec(), dry_run=True)
    assert result.url == "https://api.telegram.org/bot[redacted]/sendMessage"
    assert result.payload["parse_mode"] == "HTML"
    assert result.payload["metadata"]["provider"] == "telegram"


def test_from_env_reads_telegram_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-10012345")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")
    monkeypatch.setenv("TELEGRAM_PARSE_MODE", "HTML")

    publisher = TelegramWebhookPublisher.from_env(timeout=3.5)

    assert publisher.chat_id == "-10012345"
    assert publisher.timeout == 3.5
    result = publisher.publish(_tact_spec(), dry_run=True)
    assert result.payload["parse_mode"] == "HTML"
    assert result.payload["metadata"]["provider"] == "telegram"


def test_from_env_requires_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")

    with pytest.raises(TelegramWebhookPublishError, match="TELEGRAM_CHAT_ID"):
        TelegramWebhookPublisher.from_env()


def test_constructor_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(TelegramWebhookPublishError, match="TELEGRAM_BOT_TOKEN"):
        TelegramWebhookPublisher("12345")
