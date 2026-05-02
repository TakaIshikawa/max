"""Tests for Bitbucket Cloud issue comment publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import (
    BitbucketIssueCommentPayload,
    BitbucketIssueCommentPublisher as ExportedBitbucketIssueCommentPublisher,
    BitbucketIssueCommentPublishResult,
    BitbucketIssueCommentsPublisher,
)
from max.publisher.bitbucket_issue_comments import (
    BitbucketIssueCommentPublishError,
    BitbucketIssueCommentPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-bitbucket-comment001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
        },
        "project": {
            "title": "Bitbucket Issue Comment Publisher",
            "summary": "Append generated handoffs to existing Bitbucket issues",
        },
        "problem": {"statement": "Generated reviews can duplicate existing issues."},
        "solution": {"approach": "Post the generated handoff as an issue comment."},
        "execution": {
            "mvp_scope": ["Comment body builder", "Live publisher"],
            "validation_plan": "Publish one comment into a sandbox issue.",
        },
        "evidence": {
            "rationale": "Issue comments preserve handoff evidence in place.",
            "insight_ids": ["ins-bitbucket-comment001"],
            "signal_ids": ["sig-bitbucket-comment001"],
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
        },
    }


def test_build_comment_payload_from_string() -> None:
    publisher = BitbucketIssueCommentPublisher("max-team", "handoffs", issue_id=42)

    payload = publisher.build_comment_payload("Ship the comment publisher.").to_dict()

    assert payload["body"] == "Ship the comment publisher."
    assert payload["workspace"] == "max-team"
    assert payload["repository"] == "handoffs"
    assert payload["issue_id"] == 42
    assert payload["metadata"]["publisher"] == "max.bitbucket_issue_comments"
    assert payload["metadata"]["source_type"] == "text"


def test_build_comment_payload_from_artifact_dictionary() -> None:
    publisher = BitbucketIssueCommentPublisher(
        "max-team",
        "handoffs",
        issue_id=42,
        artifact_title="Review Artifact",
    )

    payload = publisher.build_comment_payload(_tact_spec()).to_dict()

    assert payload["body"].startswith("## Review Artifact")
    assert "Idea ID: bu-bitbucket-comment001" in payload["body"]
    assert '"kind": "tact.project_spec"' in payload["body"]
    assert payload["metadata"]["idea_id"] == "bu-bitbucket-comment001"
    assert payload["metadata"]["schema_version"] == "tact-spec-preview/v1"


def test_dry_run_returns_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketIssueCommentPublisher(
        "max-team",
        "handoffs",
        issue_id=42,
        username="agent@example.com",
        app_password="bb_app_password",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.workspace == "max-team"
    assert result.repository == "handoffs"
    assert result.issue_id == 42
    assert result.comment_id is None
    assert result.comment_url is None
    assert result.payload["metadata"]["publisher"] == "max.bitbucket_issue_comments"


def test_successful_publish_posts_bitbucket_issue_comment() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 987,
                "links": {
                    "html": {
                        "href": (
                            "https://bitbucket.org/max-team/handoffs/issues/42"
                            "#comment-987"
                        )
                    }
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketIssueCommentPublisher(
        "max-team",
        "handoffs",
        issue_id=42,
        username="agent@example.com",
        app_password="bb_app_password",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.comment_id == "987"
    assert result.comment_url == "https://bitbucket.org/max-team/handoffs/issues/42#comment-987"
    assert requests[0].url == (
        "https://api.bitbucket.org/2.0/repositories/max-team/handoffs/issues/42/comments"
    )
    expected_auth = base64.b64encode(b"agent@example.com:bb_app_password").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[0].headers["User-Agent"] == "max-bitbucket-issue-comments-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["content"]["raw"].startswith("## Bitbucket Issue Comment Publisher")
    assert result.payload["metadata"]["bitbucket_issue_comment_id"] == "987"


def test_from_env_reads_bitbucket_comment_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_WORKSPACE", "env-team")
    monkeypatch.setenv("BITBUCKET_REPOSITORY", "env-repo")
    monkeypatch.setenv("BITBUCKET_ISSUE_ID", "77")
    monkeypatch.setenv("BITBUCKET_USERNAME", "env@example.com")
    monkeypatch.setenv("BITBUCKET_APP_PASSWORD", "env_password")
    monkeypatch.setenv("BITBUCKET_BASE_URL", "https://bitbucket.example/api/2.0")

    publisher = BitbucketIssueCommentPublisher.from_env()

    assert publisher.workspace == "env-team"
    assert publisher.repository == "env-repo"
    assert publisher.issue_id == 77
    assert publisher.username == "env@example.com"
    assert publisher.app_password == "env_password"
    assert publisher.api_url == "https://bitbucket.example/api/2.0"


def test_missing_issue_id_raises_publish_error() -> None:
    publisher = BitbucketIssueCommentPublisher("max-team", "handoffs")

    with pytest.raises(BitbucketIssueCommentPublishError, match="issue_id"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_live_publish_requires_credentials() -> None:
    publisher = BitbucketIssueCommentPublisher("max-team", "handoffs", issue_id=42)

    with pytest.raises(BitbucketIssueCommentPublishError, match="BITBUCKET_USERNAME"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"error": {"message": "Not Found"}})
        )
    )
    publisher = BitbucketIssueCommentPublisher(
        "max-team",
        "handoffs",
        issue_id=42,
        username="agent@example.com",
        app_password="bb_app_password",
        client=client,
    )

    with pytest.raises(BitbucketIssueCommentPublishError, match="HTTP 404") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 404


def test_exported_from_publisher_package() -> None:
    assert ExportedBitbucketIssueCommentPublisher is BitbucketIssueCommentPublisher
    assert BitbucketIssueCommentsPublisher is BitbucketIssueCommentPublisher
    assert BitbucketIssueCommentPayload.__name__ == "BitbucketIssueCommentPayload"
    assert BitbucketIssueCommentPublishResult.__name__ == (
        "BitbucketIssueCommentPublishResult"
    )


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
