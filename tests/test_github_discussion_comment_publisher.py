from __future__ import annotations

import json

import httpx

from max.publisher.github_discussion_comments import GitHubDiscussionCommentPublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_builds_add_discussion_comment_graphql_request() -> None:
    publisher = GitHubDiscussionCommentPublisher(discussion_id="D_123", graphql_url="https://github.example/graphql")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://github.example/graphql"
    assert "addDiscussionComment" in result.payload["query"]
    assert result.payload["variables"]["discussionId"] == "D_123"
    assert "Zoom Chat Publisher" in result.payload["variables"]["body"]


def test_from_env_reads_github_discussion_comment_configuration(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_DISCUSSION_ID", "D_env")
    monkeypatch.setenv("GITHUB_GRAPHQL_URL", "https://github.example/graphql")

    publisher = GitHubDiscussionCommentPublisher.from_env()

    assert publisher.token == "gh-token"
    assert publisher.discussion_id == "D_env"
    assert publisher.graphql_url == "https://github.example/graphql"


def test_live_publish_posts_bearer_graphql_and_returns_comment_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"addDiscussionComment": {"comment": {"id": "DC_1", "url": "https://github.example/comment"}}}})

    publisher = GitHubDiscussionCommentPublisher(token="gh-token", discussion_id="D_123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.comment_id == "DC_1"
    assert result.comment_url == "https://github.example/comment"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert "addDiscussionComment" in json.loads(requests[0].read())["query"]
