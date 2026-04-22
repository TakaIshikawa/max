"""Tests for GitHub issue publishing."""

from __future__ import annotations

import httpx
import pytest

from max.publisher.github_issues import GitHubIssuePublishError, GitHubIssuePublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-test001",
            "status": "evaluated",
            "domain": "devtools",
            "category": "cli_tool",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "MCP Test Framework",
            "summary": "Standardized testing for MCP servers",
            "target_users": "developers",
            "specific_user": "MCP server maintainer",
            "buyer": "platform team",
            "workflow_context": "pre-release CI",
        },
        "problem": {"statement": "No standard way to test MCP servers"},
        "solution": {"approach": "A CLI tool that validates MCP server implementations"},
        "execution": {
            "mvp_scope": ["Protocol fixtures", "CLI runner"],
            "validation_plan": "Run with three teams.",
        },
        "evidence": {
            "rationale": "Evidence supports the idea.",
            "insight_ids": ["ins-test001"],
            "signal_ids": ["sig-test001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.5,
            "usefulness_score": 8.5,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 78.0,
            "recommendation": "yes",
            "strengths": ["High demand"],
            "weaknesses": ["Niche audience"],
        },
    }


def test_build_issue_payload_maps_tact_spec_fields() -> None:
    publisher = GitHubIssuePublisher("owner/repo")

    payload = publisher.build_issue_payload(_tact_spec()).to_dict()

    assert payload["title"] == "[Max] MCP Test Framework"
    assert "tact-spec" in payload["labels"]
    assert "cli-tool" in payload["labels"]
    assert "recommendation:yes" in payload["labels"]
    assert "Idea ID: bu-test001" in payload["body"]
    assert '"kind": "tact.project_spec"' in payload["body"]
    assert payload["metadata"]["idea_id"] == "bu-test001"
    assert payload["metadata"]["repository"] == "owner/repo"


def test_dry_run_returns_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssuePublisher("owner/repo", token="secret", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.issue_url is None
    assert result.payload["metadata"]["idea_id"] == "bu-test001"


def test_live_publish_posts_github_issue_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "number": 42,
                "html_url": "https://github.com/owner/repo/issues/42",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssuePublisher("owner/repo", token="secret", client=client)

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.issue_url == "https://github.com/owner/repo/issues/42"
    assert requests[0].url == "https://api.github.com/repos/owner/repo/issues"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    posted = json_from_request(requests[0])
    assert posted["title"] == "[Max] MCP Test Framework"
    assert "metadata" not in posted


def test_live_publish_requires_token() -> None:
    publisher = GitHubIssuePublisher("owner/repo")

    with pytest.raises(GitHubIssuePublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_reads_repository_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    publisher = GitHubIssuePublisher.from_env()

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"


def json_from_request(request: httpx.Request) -> dict:
    import json

    return json.loads(request.read())
