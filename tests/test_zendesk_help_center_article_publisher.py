from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.zendesk_help_center_articles import ZendeskHelpCenterArticlePublishError, ZendeskHelpCenterArticlePublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_builds_article_payload() -> None:
    publisher = ZendeskHelpCenterArticlePublisher(subdomain="acme", section_id="456", locale="en-us", permission_group_id="12", user_segment_id="34")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://acme.zendesk.com/api/v2/help_center/en-us/sections/456/articles.json"
    assert result.payload["article"]["title"] == "Zoom Chat Publisher"
    assert "Zoom Chat Publisher" in result.payload["article"]["body"]
    assert result.payload["article"]["draft"] is True
    assert result.payload["article"]["permission_group_id"] == "12"
    assert result.payload["article"]["user_segment_id"] == "34"


def test_from_env_reads_zendesk_article_configuration(monkeypatch) -> None:
    monkeypatch.setenv("ZENDESK_API_URL", "https://zendesk.example")
    monkeypatch.setenv("ZENDESK_EMAIL", "agent@example.com")
    monkeypatch.setenv("ZENDESK_API_TOKEN", "api-token")
    monkeypatch.setenv("ZENDESK_SECTION_ID", "789")
    monkeypatch.setenv("ZENDESK_LOCALE", "ja")

    publisher = ZendeskHelpCenterArticlePublisher.from_env()

    assert publisher.api_url == "https://zendesk.example"
    assert publisher.email == "agent@example.com"
    assert publisher.api_token == "api-token"
    assert publisher.section_id == "789"
    assert publisher.locale == "ja"


def test_live_publish_posts_basic_auth_and_returns_article_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"article": {"id": 99, "html_url": "https://help.example/articles/99"}})

    publisher = ZendeskHelpCenterArticlePublisher(api_url="https://zendesk.example", email="agent@example.com", api_token="api-token", section_id="1", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.article_id == "99"
    assert result.article_url == "https://help.example/articles/99"
    expected = base64.b64encode(b"agent@example.com/token:api-token").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected}"
    assert json.loads(requests[0].read())["article"]["locale"] == "en-us"


def test_validates_section_id_and_api_url() -> None:
    with pytest.raises(ValueError, match="section_id"):
        ZendeskHelpCenterArticlePublisher(api_url="https://zendesk.example", section_id="")
    with pytest.raises(ZendeskHelpCenterArticlePublishError, match="api_url"):
        ZendeskHelpCenterArticlePublisher(api_url="not a url / path", section_id="1")


