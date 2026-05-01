"""Tests for GitHub issue comment publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    GitHubIssueCommentPublisher as ExportedGitHubIssueCommentPublisher,
)
from max.publisher.github_issue_comments import (
    GitHubIssueCommentPublishError,
    GitHubIssueCommentPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-comment001",
            "status": "approved",
            "domain": "devtools",
            "category": "cli_tool",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "GitHub Issue Comment Publisher",
            "summary": "Append generated summaries to existing tracking issues",
            "target_users": "operators",
            "specific_user": "product engineer",
            "buyer": "platform team",
            "workflow_context": "issue triage",
        },
        "problem": {"statement": "Generated ideas can duplicate existing issues."},
        "solution": {"approach": "Post the generated handoff as an issue comment."},
        "execution": {
            "mvp_scope": ["Comment body builder", "Live publisher"],
            "validation_plan": "Publish one comment into a sandbox issue.",
        },
        "evidence": {
            "rationale": "Issue comments preserve handoff evidence in place.",
            "insight_ids": ["ins-comment001"],
            "signal_ids": ["sig-comment001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
        },
    }


def test_dry_run_returns_comment_body_target_and_issue_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssueCommentPublisher(
        "owner/repo",
        issue_number=42,
        token="secret",
        artifact_title="Review Artifact",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.repository == "owner/repo"
    assert result.issue_number == 42
    assert result.comment_id is None
    assert result.comment_url is None
    assert result.payload["repository"] == "owner/repo"
    assert result.payload["issue_number"] == 42
    assert result.payload["body"].startswith("## Review Artifact")
    assert "Idea ID: bu-comment001" in result.payload["body"]
    assert '"kind": "tact.project_spec"' in result.payload["body"]
    assert result.payload["metadata"]["publisher"] == "max.github_issue_comments"


def test_build_comment_body_is_deterministic() -> None:
    publisher = GitHubIssueCommentPublisher("owner/repo", issue_number=42)

    first = publisher.build_comment_payload(_tact_spec()).to_dict()
    second = publisher.build_comment_payload(_tact_spec()).to_dict()

    assert first["body"] == second["body"]
    assert first["body"].startswith("## GitHub Issue Comment Publisher")


def test_successful_publish_posts_issue_comment_and_returns_id_and_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 98765,
                "html_url": "https://github.com/owner/repo/issues/42#issuecomment-98765",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssueCommentPublisher(
        "owner/repo",
        issue_number=42,
        token="secret",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.comment_id == "98765"
    assert (
        result.comment_url
        == "https://github.com/owner/repo/issues/42#issuecomment-98765"
    )
    assert requests[0].url == "https://api.github.com/repos/owner/repo/issues/42/comments"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert requests[0].headers["User-Agent"] == "max-github-issue-comments-publisher/1"
    posted = _json_from_request(requests[0])
    assert list(posted) == ["body"]
    assert posted["body"].startswith("## GitHub Issue Comment Publisher")
    assert result.payload["metadata"]["github_issue_comment_id"] == "98765"


def test_missing_issue_number_raises_publish_error() -> None:
    publisher = GitHubIssueCommentPublisher("owner/repo")

    with pytest.raises(GitHubIssueCommentPublishError, match="issue number"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"message": "Not Found"})
        )
    )
    publisher = GitHubIssueCommentPublisher(
        "owner/repo",
        issue_number=42,
        token="secret",
        client=client,
    )

    with pytest.raises(GitHubIssueCommentPublishError, match="HTTP 404") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 404


def test_exported_from_publisher_package() -> None:
    assert ExportedGitHubIssueCommentPublisher is GitHubIssueCommentPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
