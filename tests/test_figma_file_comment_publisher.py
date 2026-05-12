from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.figma_file_comments import FigmaFileCommentPublishError, FigmaFileCommentPublisher
from tests.test_zoom_chat_webhook_publisher import _design_brief_payload, _idea_payload


def test_dry_run_returns_figma_endpoint_and_payload_without_token() -> None:
    publisher = FigmaFileCommentPublisher(file_key="file 123", api_url="https://figma.example.test", comment_node_id="1:2")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://figma.example.test/v1/files/file%20123/comments"
    assert "Zoom Chat Publisher" in result.payload["message"]
    assert result.payload["client_meta"] == {"node_id": "1:2"}


def test_from_env_reads_figma_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIGMA_ACCESS_TOKEN", "fig-token")
    monkeypatch.setenv("FIGMA_FILE_KEY", "abc123")
    monkeypatch.setenv("FIGMA_COMMENT_NODE_ID", "9:8")
    monkeypatch.setenv("FIGMA_API_URL", "https://figma.example.test")

    publisher = FigmaFileCommentPublisher.from_env()

    assert publisher.access_token == "fig-token"
    assert publisher.file_key == "abc123"
    assert publisher.comment_node_id == "9:8"
    assert publisher.api_url == "https://figma.example.test"


def test_live_publish_posts_bearer_header_and_returns_comment_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"comment": {"id": "comment-1"}})

    publisher = FigmaFileCommentPublisher(access_token="fig-token", file_key="abc123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_design_brief_payload(), dry_run=False)

    assert result.comment_id == "comment-1"
    assert requests[0].headers["Authorization"] == "Bearer fig-token"
    assert "Zoom Chat Design Brief" in json.loads(requests[0].read())["message"]


def test_live_publish_error_redacts_token() -> None:
    publisher = FigmaFileCommentPublisher(access_token="fig-token", file_key="abc123", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="bad fig-token"))))

    with pytest.raises(FigmaFileCommentPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 401
    assert "fig-token" not in str(exc.value)
