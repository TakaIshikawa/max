"""Tests for Jira issue comment publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import (
    JiraIssueCommentPublisher as ExportedJiraIssueCommentPublisher,
)
from max.publisher.jira_issue_comments import (
    JiraIssueCommentPublishError,
    JiraIssueCommentPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-jira-comment001",
            "status": "approved",
        },
        "project": {
            "title": "Jira Issue Comment Publisher",
            "summary": "Append generated specs to existing planning tickets",
        },
    }


def test_comment_endpoint_uses_issue_key() -> None:
    publisher = JiraIssueCommentPublisher(
        "https://example.atlassian.net/",
        issue_key="MAX-42",
    )

    assert (
        publisher.comment_endpoint()
        == "https://example.atlassian.net/rest/api/3/issue/MAX-42/comment"
    )


def test_dry_run_returns_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssueCommentPublisher(
        "https://example.atlassian.net",
        issue_key="MAX-42",
        auth_email="agent@example.com",
        api_token="jira_api_token",
        visibility_type="role",
        visibility_value="Developers",
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        markdown="## Generated Spec\n\nShip the comment publisher.",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.status_code is None
    assert result.issue_key == "MAX-42"
    assert result.comment_id is None
    assert result.comment_url is None
    assert result.payload["body"] == "## Generated Spec\n\nShip the comment publisher."
    assert result.payload["visibility"] == {"type": "role", "value": "Developers"}
    assert result.payload["metadata"]["publisher"] == "max.jira_issue_comments"


def test_successful_publish_posts_comment_and_returns_id_issue_key_and_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": "10001",
                "self": "https://example.atlassian.net/rest/api/3/issue/10042/comment/10001",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssueCommentPublisher(
        "https://example.atlassian.net",
        issue_key="MAX-42",
        auth_email="agent@example.com",
        api_token="jira_api_token",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.issue_key == "MAX-42"
    assert result.comment_id == "10001"
    assert result.comment_url == (
        "https://example.atlassian.net/browse/MAX-42?focusedCommentId=10001"
    )
    assert requests[0].url == (
        "https://example.atlassian.net/rest/api/3/issue/MAX-42/comment"
    )
    expected_auth = base64.b64encode(b"agent@example.com:jira_api_token").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[0].headers["User-Agent"] == "max-jira-issue-comments-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["body"]["type"] == "doc"
    assert posted["body"]["content"][0]["type"] == "heading"
    assert result.payload["metadata"]["jira_issue_comment_id"] == "10001"


def test_live_publish_uses_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "10001"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssueCommentPublisher(
        "https://example.atlassian.net",
        issue_key="MAX-42",
        bearer_token="jira_bearer",
        client=client,
    )

    publisher.publish(_tact_spec(), dry_run=False)

    assert requests[0].headers["Authorization"] == "Bearer jira_bearer"


def test_missing_issue_key_raises_publish_error() -> None:
    publisher = JiraIssueCommentPublisher("https://example.atlassian.net")

    with pytest.raises(JiraIssueCommentPublishError, match="issue_key"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_live_publish_requires_credentials() -> None:
    publisher = JiraIssueCommentPublisher(
        "https://example.atlassian.net",
        issue_key="MAX-42",
    )

    with pytest.raises(JiraIssueCommentPublishError, match="auth_email/api_token"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"error": "Not Found"})
        )
    )
    publisher = JiraIssueCommentPublisher(
        "https://example.atlassian.net",
        issue_key="MAX-42",
        bearer_token="jira_bearer",
        client=client,
    )

    with pytest.raises(JiraIssueCommentPublishError, match="HTTP 404") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 404


def test_exported_from_publisher_package() -> None:
    assert ExportedJiraIssueCommentPublisher is JiraIssueCommentPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
