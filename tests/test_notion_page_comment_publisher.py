from __future__ import annotations

import json

import httpx

from max.publisher.notion_page_comments import NotionPageCommentPublisher
from tests.test_zoom_chat_webhook_publisher import _design_brief_payload, _idea_payload


def test_dry_run_returns_notion_comments_endpoint_and_rich_text_for_inputs() -> None:
    publisher = NotionPageCommentPublisher(page_id="page-1", api_url="https://notion.example.test/v1")

    idea = publisher.publish(_idea_payload(), dry_run=True)
    brief = publisher.publish(_design_brief_payload(), dry_run=True)

    assert idea.endpoint == "https://notion.example.test/v1/comments"
    assert "Zoom Chat Publisher" in idea.payload["rich_text"][0]["text"]["content"]
    assert "Zoom Chat Design Brief" in brief.payload["rich_text"][0]["text"]["content"]
    assert idea.payload["parent"] == {"page_id": "page-1"}


def test_from_env_reads_notion_page_comment_configuration(monkeypatch) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "notion-token")
    monkeypatch.setenv("NOTION_PAGE_ID", "page-env")
    monkeypatch.setenv("NOTION_API_URL", "https://notion.example.test/v1")
    monkeypatch.setenv("NOTION_VERSION", "2023-01-01")

    publisher = NotionPageCommentPublisher.from_env()

    assert publisher.token == "notion-token"
    assert publisher.page_id == "page-env"
    assert publisher.api_url == "https://notion.example.test/v1"
    assert publisher.notion_version == "2023-01-01"


def test_live_publish_sends_notion_headers_and_returns_comment_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "comment-1"})

    publisher = NotionPageCommentPublisher(token="notion-token", page_id="page-1", notion_version="2023-01-01", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.comment_id == "comment-1"
    assert requests[0].headers["Authorization"] == "Bearer notion-token"
    assert requests[0].headers["Notion-Version"] == "2023-01-01"
    assert json.loads(requests[0].read())["parent"]["page_id"] == "page-1"
