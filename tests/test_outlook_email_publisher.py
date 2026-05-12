from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.outlook_email import OutlookEmailPublishError, OutlookEmailPublisher
from tests.test_zoom_chat_webhook_publisher import _design_brief_payload, _idea_payload


def test_builds_idea_sendmail_payload() -> None:
    publisher = OutlookEmailPublisher(to=["buyer@example.com"], cc="team@example.com", subject_prefix="[Max]")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://graph.microsoft.com/v1.0/me/sendMail"
    assert result.payload["message"]["subject"] == "[Max] Zoom Chat Publisher"
    assert result.payload["message"]["toRecipients"][0]["emailAddress"]["address"] == "buyer@example.com"
    assert result.payload["message"]["ccRecipients"][0]["emailAddress"]["address"] == "team@example.com"
    assert "Publish Max ideas into Zoom Team Chat." in result.payload["plainTextBody"]


def test_builds_design_brief_payload_and_user_endpoint() -> None:
    publisher = OutlookEmailPublisher(sender_user_id="sender@example.com", to="buyer@example.com")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.endpoint == "https://graph.microsoft.com/v1.0/users/sender%40example.com/sendMail"
    assert result.payload["message"]["subject"] == "Zoom Chat Design Brief"
    assert "Readiness score: 88.0" in result.payload["plainTextBody"]
    assert "bu-zoom001, bu-supporting" in result.payload["plainTextBody"]


def test_rejects_empty_recipient_set() -> None:
    publisher = OutlookEmailPublisher()

    with pytest.raises(OutlookEmailPublishError, match="recipient"):
        publisher.publish(_idea_payload(), dry_run=True)


def test_from_env_reads_outlook_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "token")
    monkeypatch.setenv("OUTLOOK_TO", "a@example.com,b@example.com")
    monkeypatch.setenv("OUTLOOK_SUBJECT_PREFIX", "[Env]")
    monkeypatch.setenv("MICROSOFT_GRAPH_API_URL", "https://graph.example.test/v1.0")

    publisher = OutlookEmailPublisher.from_env()

    assert publisher.access_token == "token"
    assert publisher.to == ["a@example.com", "b@example.com"]
    assert publisher.subject_prefix == "[Env]"
    assert publisher.graph_api_url == "https://graph.example.test/v1.0"


def test_live_publish_accepts_202_and_posts_graph_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202)

    publisher = OutlookEmailPublisher(access_token="token", to="buyer@example.com", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 202
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert "plainTextBody" not in json.loads(requests[0].read())


def test_live_publish_raises_redacted_error() -> None:
    publisher = OutlookEmailPublisher(access_token="token", to="buyer@example.com", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400, text="bad token"))))

    with pytest.raises(OutlookEmailPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 400
    assert "token" not in str(exc.value)
