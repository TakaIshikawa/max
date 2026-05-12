"""Tests for Zoom Team Chat webhook publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.zoom_chat_webhook import (
    ZoomChatWebhookPublishError,
    ZoomChatWebhookPublisher,
    publish_zoom_chat_webhook,
)


def _idea_payload() -> dict:
    return {
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-zoom001",
            "status": "approved",
            "domain": "devtools",
            "category": "collaboration",
        },
        "project": {
            "title": "Zoom Chat Publisher",
            "summary": "Publish Max ideas into Zoom Team Chat.",
        },
        "execution": {"validation_plan": "Send one dry run and one live webhook."},
        "evidence": {
            "insight_ids": ["ins-zoom001"],
            "signal_ids": ["sig-zoom001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {"quality_score": 8.0},
        "evaluation": {"overall_score": 82.0, "recommendation": "ship"},
    }


def _design_brief_payload() -> dict:
    return {
        "source": {"entity_type": "design_brief", "id": "dbf-zoom001"},
        "design_brief": {
            "id": "dbf-zoom001",
            "title": "Zoom Chat Design Brief",
            "summary": "Publish design briefs to Zoom Team Chat.",
            "readiness_score": 88.0,
            "recommendation": "ready",
            "design_status": "draft",
            "lead_idea_id": "bu-zoom001",
            "source_idea_ids": ["bu-zoom001", "bu-supporting"],
            "markdown": "# Zoom Chat Design Brief\n\nA concise rendered preview.",
        },
        "evidence_refs": {"insight_ids": ["ins-zoom001"], "signal_ids": ["sig-zoom001"]},
    }


def _body_texts(payload: dict) -> list[str]:
    return [item["text"] for item in payload["content"]["body"]]


def test_idea_payload_renders_zoom_message() -> None:
    publisher = ZoomChatWebhookPublisher("https://example.zoom.us/webhook/secret?token=top-secret")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.payload["content"]["head"]["text"] == "[Max] Zoom Chat Publisher"
    assert "*Summary:* Publish Max ideas into Zoom Team Chat." in _body_texts(result.payload)
    assert "*Score:* 82.0" in _body_texts(result.payload)
    assert "*Recommendation:* ship" in _body_texts(result.payload)
    assert "*Idea ID:* bu-zoom001" in _body_texts(result.payload)
    assert "insights=ins-zoom001" in "\n".join(_body_texts(result.payload))
    assert result.payload["metadata"]["publisher"] == "max.zoom_chat_webhook"
    assert result.payload["metadata"]["idea_id"] == "bu-zoom001"


def test_design_brief_payload_renders_zoom_message_with_markdown_preview() -> None:
    publisher = ZoomChatWebhookPublisher("https://example.zoom.us/webhook/secret?token=top-secret")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    text = "\n".join(_body_texts(result.payload))
    assert result.payload["content"]["head"]["text"] == "[Max] Zoom Chat Design Brief"
    assert "*Brief ID:* dbf-zoom001" in text
    assert "*Readiness:* 88.0" in text
    assert "*Recommendation:* ready" in text
    assert "*Source ideas:* bu-zoom001, bu-supporting" in text
    assert "# Zoom Chat Design Brief" in text
    assert result.payload["metadata"]["source_type"] == "design_brief"
    assert result.payload["metadata"]["source_idea_ids"] == ["bu-zoom001", "bu-supporting"]


def test_dry_run_returns_redacted_url_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ZoomChatWebhookPublisher(
        "https://user:password@example.zoom.us/webhook/path-secret?token=query-secret",
        client=client,
    )

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.status_code is None
    assert result.url == "https://***@example.zoom.us/webhook/[redacted]?[redacted]"
    assert "query-secret" not in result.url
    assert "path-secret" not in result.url
    assert result.payload_preview.startswith("[Max] Zoom Chat Publisher")


def test_live_publish_posts_zoom_json_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text='{"ok":true}', headers={"x-request-id": "zoom-req"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ZoomChatWebhookPublisher(
        "https://example.zoom.us/webhook/path-secret?token=query-secret",
        client=client,
    )

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.response_body == '{"ok":true}'
    assert result.url == "https://example.zoom.us/webhook/[redacted]?[redacted]"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted["metadata"]["provider"] == "zoom_chat"
    assert posted["content"]["head"]["text"] == "[Max] Zoom Chat Publisher"


def test_publish_zoom_chat_webhook_helper_posts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = publish_zoom_chat_webhook(
        _idea_payload(),
        webhook_url="https://example.zoom.us/webhook/path-secret?token=query-secret",
        dry_run=False,
        client=client,
    )

    assert result.status_code == 204
    assert json.loads(requests[0].read())["metadata"]["idea_id"] == "bu-zoom001"


def test_live_publish_raises_for_zoom_error_response_and_redacts_url_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text="denied path-secret token=query-secret https://example.zoom.us/webhook/path-secret?token=query-secret",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ZoomChatWebhookPublisher(
        "https://example.zoom.us/webhook/path-secret?token=query-secret",
        client=client,
    )

    with pytest.raises(ZoomChatWebhookPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    message = str(exc.value)
    assert exc.value.status_code == 403
    assert "path-secret" not in message
    assert "query-secret" not in message
    assert "denied" in message


def test_request_error_redacts_webhook_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "failed https://example.zoom.us/webhook/path-secret?token=query-secret",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ZoomChatWebhookPublisher(
        "https://example.zoom.us/webhook/path-secret?token=query-secret",
        client=client,
    )

    with pytest.raises(ZoomChatWebhookPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert "path-secret" not in str(exc.value)
    assert "query-secret" not in str(exc.value)


def test_invalid_webhook_url_is_structured_failure() -> None:
    with pytest.raises(ZoomChatWebhookPublishError, match="absolute http"):
        ZoomChatWebhookPublisher("not-a-url")
