"""Tests for Linear issue comment publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    LinearIssueCommentPublisher as ExportedLinearIssueCommentPublisher,
)
from max.publisher.linear_issue_comments import (
    LinearIssueCommentPublishError,
    LinearIssueCommentPublisher,
)


def _artifact() -> dict:
    return {
        "schema_version": "design-brief-scope-matrix/v1",
        "kind": "max.design_brief.scope_matrix",
        "source": {
            "system": "max",
            "type": "design_brief",
            "idea_id": "bu-linear-comment",
            "design_brief_id": "dbf-linear-comment",
        },
        "project": {
            "title": "Linear Comment Artifact",
            "summary": "Attach generated planning artifacts to Linear issues.",
        },
    }


def test_build_comment_payload_maps_issue_key_and_artifact_markdown() -> None:
    publisher = LinearIssueCommentPublisher(issue_key="MAX-42")

    payload = publisher.build_comment_payload(_artifact()).to_dict()

    assert payload["issue_key"] == "MAX-42"
    assert payload["body"].startswith("## Linear Comment Artifact")
    assert "Attach generated planning artifacts to Linear issues." in payload["body"]
    assert "- Kind: max.design_brief.scope_matrix" in payload["body"]
    assert "- Schema version: design-brief-scope-matrix/v1" in payload["body"]
    assert payload["metadata"]["publisher"] == "max.linear_issue_comments"
    assert payload["metadata"]["design_brief_id"] == "dbf-linear-comment"


def test_dry_run_returns_linear_comment_create_request_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = LinearIssueCommentPublisher(
        issue_id="issue-123",
        api_key="lin_secret",
        client=client,
    )

    result = publisher.publish("Review note", dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.issue_id == "issue-123"
    assert result.issue_key is None
    assert result.comment_id is None
    assert result.payload["request"]["method"] == "POST"
    assert result.payload["request"]["url"] == "https://api.linear.app/graphql"
    assert "commentCreate" in result.payload["request"]["json"]["query"]
    assert result.payload["request"]["json"]["variables"]["input"] == {
        "issueId": "issue-123",
        "body": "Review note",
    }
    assert "lin_secret" not in json.dumps(result.payload["request"])


def test_from_env_reads_issue_key_api_key_and_artifact_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINEAR_ISSUE_KEY", "MAX-43")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_env")
    monkeypatch.setenv("LINEAR_ARTIFACT_TITLE", "Env Artifact Title")

    publisher = LinearIssueCommentPublisher.from_env()
    payload = publisher.build_comment_payload(_artifact()).to_dict()

    assert publisher.issue_key == "MAX-43"
    assert publisher.api_key == "lin_env"
    assert payload["body"].startswith("## Env Artifact Title")


def test_explicit_body_overrides_artifact_markdown() -> None:
    publisher = LinearIssueCommentPublisher(issue_id="issue-123")

    payload = publisher.build_comment_payload(_artifact(), body="Ship this follow-up").to_dict()

    assert payload["body"] == "Ship this follow-up"
    assert payload["metadata"]["kind"] == "max.design_brief.scope_matrix"


def test_successful_publish_posts_linear_comment_create_and_normalizes_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "commentCreate": {
                        "success": True,
                        "comment": {
                            "id": "comment-123",
                            "url": "https://linear.app/max/comment/comment-123",
                            "issue": {
                                "id": "issue-123",
                                "identifier": "MAX-42",
                                "url": "https://linear.app/max/issue/MAX-42/example",
                            },
                        },
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = LinearIssueCommentPublisher(
        issue_key="MAX-42",
        api_key="lin_api",
        client=client,
    )

    result = publisher.publish("Review note", dry_run=False)

    assert result.status_code == 200
    assert result.issue_id == "issue-123"
    assert result.issue_key == "MAX-42"
    assert result.comment_id == "comment-123"
    assert result.comment_url == "https://linear.app/max/comment/comment-123"
    assert requests[0].url == "https://api.linear.app/graphql"
    assert requests[0].headers["Authorization"] == "lin_api"
    assert requests[0].headers["User-Agent"] == "max-linear-issue-comments-publisher/1"
    posted = _json_from_request(requests[0])
    assert "commentCreate" in posted["query"]
    assert posted["variables"]["input"] == {
        "issueId": "MAX-42",
        "body": "Review note",
    }
    assert result.payload["metadata"]["linear_issue_comment_id"] == "comment-123"


def test_live_publish_raises_redacted_error_on_http_failure() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                json={"message": "bad token lin_secret"},
            )
        )
    )
    publisher = LinearIssueCommentPublisher(
        issue_id="issue-123",
        api_key="lin_secret",
        client=client,
    )

    with pytest.raises(LinearIssueCommentPublishError, match="HTTP 401") as exc:
        publisher.publish("Review note", dry_run=False)

    assert exc.value.status_code == 401
    assert "lin_secret" not in str(exc.value)


def test_live_publish_raises_redacted_error_on_graphql_errors() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"errors": [{"message": "token lin_secret cannot access issue"}]},
            )
        )
    )
    publisher = LinearIssueCommentPublisher(
        issue_key="MAX-42",
        api_key="lin_secret",
        client=client,
    )

    with pytest.raises(LinearIssueCommentPublishError, match="cannot access issue") as exc:
        publisher.publish("Review note", dry_run=False)

    assert exc.value.status_code == 200
    assert "lin_secret" not in str(exc.value)


def test_missing_issue_identifier_raises_validation_error() -> None:
    publisher = LinearIssueCommentPublisher(api_key="lin_api")

    with pytest.raises(LinearIssueCommentPublishError, match="issue_id or issue_key"):
        publisher.publish("Review note", dry_run=True)


def test_exported_from_publisher_package() -> None:
    assert ExportedLinearIssueCommentPublisher is LinearIssueCommentPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
