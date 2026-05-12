from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.jira_issue_attachments import JiraIssueAttachmentPublishError, JiraIssueAttachmentPublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_builds_markdown_attachment_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not call Jira")

    publisher = JiraIssueAttachmentPublisher("https://max.atlassian.net", issue_key="MAX-1", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=True, filename="idea.md")

    assert result.status_code is None
    assert result.issue_key == "MAX-1"
    assert result.filename == "idea.md"
    assert result.payload["content_type"] == "text/markdown"
    assert "# Zoom Chat Publisher" in result.payload["content_preview"]
    assert result.payload["metadata"]["idea_id"] == "bu-zoom001"


def test_builds_json_attachment_from_explicit_content() -> None:
    publisher = JiraIssueAttachmentPublisher("https://max.atlassian.net", issue_key="MAX-1")

    payload = publisher.build_attachment_payload({"source": {"idea_id": "idea-1"}}, filename="payload.json", content='{"ok": true}')

    assert payload.content_type == "application/json"
    assert json.loads(payload.content.decode()) == {"ok": True}
    assert payload.metadata["filename"] == "payload.json"


def test_live_publish_posts_multipart_with_jira_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[{"id": "10001", "content": "https://max.atlassian.net/attachment/10001"}])

    publisher = JiraIssueAttachmentPublisher(
        "https://max.atlassian.net",
        issue_key="MAX-2",
        auth_email="user@example.com",
        api_token="token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish("hello", dry_run=False, filename="note.md")

    assert result.status_code == 200
    assert result.attachment_id == "10001"
    assert requests[0].url.path == "/rest/api/3/issue/MAX-2/attachments"
    assert requests[0].headers["X-Atlassian-Token"] == "no-check"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert b'name="file"; filename="note.md"' in requests[0].read()


def test_validation_and_live_auth_errors() -> None:
    with pytest.raises(JiraIssueAttachmentPublishError, match="absolute http"):
        JiraIssueAttachmentPublisher("not-a-url")
    publisher = JiraIssueAttachmentPublisher("https://max.atlassian.net")
    with pytest.raises(JiraIssueAttachmentPublishError, match="issue_key"):
        publisher.publish("hello", dry_run=True)
    publisher = JiraIssueAttachmentPublisher("https://max.atlassian.net", issue_key="MAX-1")
    with pytest.raises(JiraIssueAttachmentPublishError, match="auth"):
        publisher.publish("hello", dry_run=False)
