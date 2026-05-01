"""Tests for GitHub pull request review comment publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    GitHubPullRequestReviewCommentPublisher as ExportedGitHubPullRequestReviewCommentPublisher,
)
from max.publisher.github_pull_request_review_comments import (
    GitHubPullRequestReviewCommentPublishError,
    GitHubPullRequestReviewCommentPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "idea_id": "bu-review001",
            "design_brief_id": "dbf-review001",
            "status": "approved",
            "domain": "devtools",
            "category": "review_workflow",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "GitHub PR Review Publisher",
            "summary": "Attach generated implementation notes directly to PR review flows.",
            "target_users": "product engineers",
            "specific_user": "review owner",
            "buyer": "platform team",
            "workflow_context": "implementation review",
        },
        "problem": {"statement": "Generated specs are detached from code review."},
        "solution": {"approach": "Create a comment-only pull request review."},
        "execution": {
            "mvp_scope": ["Review body builder", "Inline comment support"],
            "validation_plan": "Publish one review into a sandbox pull request.",
        },
        "evidence": {
            "rationale": "Review comments preserve spec context at the implementation point.",
            "insight_ids": ["ins-review001"],
            "signal_ids": ["sig-review001"],
        },
        "quality": {"quality_score": 8.0, "rejection_tags": []},
        "evaluation": {"overall_score": 86.0, "recommendation": "yes"},
    }


def _design_brief() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-pr-review",
            "title": "Review Workflow Handoff",
            "domain": "devtools",
            "theme": "pull-request-review",
            "lead_idea_id": "bu-lead",
            "source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"],
            "readiness_score": 91.5,
            "design_status": "ready",
            "merged_product_concept": "Publish brief summaries into GitHub PR reviews.",
            "validation_plan": "Create one comment-only review.",
        },
    }


def test_dry_run_returns_review_target_body_event_and_comments_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    comments = [
        {
            "path": "src/max/publisher/github.py",
            "line": 24,
            "side": "RIGHT",
            "body": "Consider linking this to the generated review summary.",
        }
    ]
    publisher = GitHubPullRequestReviewCommentPublisher(
        "owner/repo",
        pull_number=42,
        token="secret",
        commit_id="abc123",
        comments=comments,
        artifact_title="Implementation Review",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.owner == "owner"
    assert result.repo == "repo"
    assert result.repository == "owner/repo"
    assert result.pull_number == 42
    assert result.review_id is None
    assert result.review_state is None
    assert result.review_url is None
    assert result.payload["owner"] == "owner"
    assert result.payload["repo"] == "repo"
    assert result.payload["repository"] == "owner/repo"
    assert result.payload["pull_number"] == 42
    assert result.payload["event"] == "COMMENT"
    assert result.payload["commit_id"] == "abc123"
    assert result.payload["comments"] == comments
    assert result.payload["body"].startswith("## Implementation Review")
    assert "Design brief ID: dbf-review001" in result.payload["body"]
    assert '"kind": "tact.project_spec"' in result.payload["body"]
    assert result.payload["metadata"]["publisher"] == (
        "max.github_pull_request_review_comments"
    )


def test_build_design_brief_payload_maps_markdown_summary_and_source_metadata() -> None:
    publisher = GitHubPullRequestReviewCommentPublisher("owner/repo", pull_number=42)

    payload = publisher.build_design_brief_payload(
        _design_brief(),
        markdown="# Review Workflow Handoff",
    ).to_dict()

    assert payload["body"].startswith("## Review Workflow Handoff")
    assert "Publish brief summaries into GitHub PR reviews." in payload["body"]
    assert "# Review Workflow Handoff" in payload["body"]
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-pr-review"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-supporting"]


def test_live_publish_posts_expected_pull_request_review_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": 98765,
                "state": "COMMENTED",
                "html_url": "https://github.com/owner/repo/pull/42#pullrequestreview-98765",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubPullRequestReviewCommentPublisher(
        "owner/repo",
        pull_number=42,
        token="secret",
        review_body="Generated review summary",
        commit_id="abc123",
        comments=[
            {
                "path": "src/max/publisher/github.py",
                "line": 24,
                "side": "RIGHT",
                "body": "Inline implementation note.",
            }
        ],
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.review_id == "98765"
    assert result.review_state == "COMMENTED"
    assert result.review_url == (
        "https://github.com/owner/repo/pull/42#pullrequestreview-98765"
    )
    assert requests[0].url == "https://api.github.com/repos/owner/repo/pulls/42/reviews"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert requests[0].headers["User-Agent"] == (
        "max-github-pull-request-review-comments-publisher/1"
    )
    posted = _json_from_request(requests[0])
    assert posted == {
        "body": "Generated review summary",
        "event": "COMMENT",
        "commit_id": "abc123",
        "comments": [
            {
                "path": "src/max/publisher/github.py",
                "line": 24,
                "side": "RIGHT",
                "body": "Inline implementation note.",
            }
        ],
    }
    assert result.payload["metadata"]["github_pull_request_review_id"] == "98765"
    assert result.payload["metadata"]["github_pull_request_review_state"] == "COMMENTED"


def test_from_env_reads_github_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_PULL_NUMBER", "77")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_PULL_REQUEST_REVIEW_BODY", "Env review body")
    monkeypatch.setenv("GITHUB_PULL_REQUEST_COMMIT_ID", "def456")

    publisher = GitHubPullRequestReviewCommentPublisher.from_env()
    result = publisher.publish(_tact_spec(), dry_run=True)

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"
    assert result.pull_number == 77
    assert result.payload["body"] == "Env review body"
    assert result.payload["commit_id"] == "def456"


def test_missing_pull_number_raises_publish_error() -> None:
    publisher = GitHubPullRequestReviewCommentPublisher("owner/repo")

    with pytest.raises(GitHubPullRequestReviewCommentPublishError, match="pull number"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_live_publish_requires_token() -> None:
    publisher = GitHubPullRequestReviewCommentPublisher("owner/repo", pull_number=42)

    with pytest.raises(GitHubPullRequestReviewCommentPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(422, json={"message": "Validation Failed"})
        )
    )
    publisher = GitHubPullRequestReviewCommentPublisher(
        "owner/repo",
        pull_number=42,
        token="secret",
        client=client,
    )

    with pytest.raises(GitHubPullRequestReviewCommentPublishError, match="HTTP 422") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 422


def test_exported_from_publisher_package() -> None:
    assert ExportedGitHubPullRequestReviewCommentPublisher is (
        GitHubPullRequestReviewCommentPublisher
    )


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
