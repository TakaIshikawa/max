from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.dropbox_paper_doc_comments import DropboxPaperDocCommentPublishError, DropboxPaperDocCommentPublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_returns_endpoint_redacted_headers_payload_and_markdown_without_token() -> None:
    publisher = DropboxPaperDocCommentPublisher(doc_id="paper doc", api_url="https://dropbox.example.test/2")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://dropbox.example.test/2/paper/docs/paper%20doc/comments"
    assert "Authorization" not in result.headers
    assert result.payload["comment"]["format"] == "markdown"
    assert result.payload["comment"]["text"] == result.markdown
    assert "Zoom Chat Publisher" in result.markdown
    assert result.payload["metadata"]["publisher"] == "max.dropbox_paper_doc_comments"


def test_from_env_reads_dropbox_comment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DROPBOX_ACCESS_TOKEN", "drop-token")
    monkeypatch.setenv("DROPBOX_PAPER_DOC_ID", "doc-1")
    monkeypatch.setenv("DROPBOX_API_URL", "https://dropbox.example.test/2")

    publisher = DropboxPaperDocCommentPublisher.from_env()

    assert publisher.access_token == "drop-token"
    assert publisher.doc_id == "doc-1"
    assert publisher.api_url == "https://dropbox.example.test/2"


def test_live_publish_posts_comment_and_returns_comment_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"comment_id": "comment-1", "url": "https://paper.example/comment-1"})

    publisher = DropboxPaperDocCommentPublisher(access_token="drop-token", doc_id="doc-1", api_url="https://dropbox.example.test/2", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.comment_id == "comment-1"
    assert result.comment_url == "https://paper.example/comment-1"
    assert result.headers["Authorization"] == "Bearer [REDACTED]"
    assert requests[0].url == "https://dropbox.example.test/2/paper/docs/doc-1/comments"
    assert requests[0].headers["Authorization"] == "Bearer drop-token"
    assert json.loads(requests[0].read())["comment"]["format"] == "markdown"


def test_live_publish_requires_token_and_doc_id_before_http_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("configuration validation should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(DropboxPaperDocCommentPublishError, match="DROPBOX_ACCESS_TOKEN"):
        DropboxPaperDocCommentPublisher(doc_id="doc-1", client=client).publish(_idea_payload(), dry_run=False)
    with pytest.raises(ValueError, match="DROPBOX_PAPER_DOC_ID"):
        DropboxPaperDocCommentPublisher(access_token="drop-token", client=client).publish(_idea_payload(), dry_run=False)


def test_live_publish_error_includes_status_preview_and_redacts_token() -> None:
    publisher = DropboxPaperDocCommentPublisher(access_token="drop-token", doc_id="doc-1", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text="denied drop-token"))))

    with pytest.raises(DropboxPaperDocCommentPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 403
    assert "HTTP 403" in str(exc.value)
    assert "denied" in str(exc.value)
    assert "drop-token" not in str(exc.value)
