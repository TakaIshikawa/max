"""Tests for GitHub issue label publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import GitHubIssueLabelsPublisher as ExportedGitHubIssueLabelsPublisher
from max.publisher.github_issue_labels import (
    GitHubIssueLabelPublishError,
    GitHubIssueLabelsPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-label001",
            "status": "approved",
            "domain": "devtools",
            "category": "triage_automation",
        },
        "quality": {
            "quality_score": 8.0,
            "rejection_tags": ["needs_evidence"],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
        },
    }


def _design_brief() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-label001",
            "title": "Labels Design Brief",
            "domain": "devtools",
            "theme": "triage-routing",
            "lead_idea_id": "bu-lead",
            "source_idea_ids": ["bu-lead", "bu-support", "bu-lead"],
            "design_status": "ready_for_build",
        },
    }


def test_dry_run_returns_target_labels_and_api_url_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssueLabelsPublisher(
        "owner/repo",
        issue_number=42,
        token="secret",
        api_url="https://api.github.test",
        labels=["Max", "team:agents"],
        client=client,
    )

    result = publisher.publish(_tact_spec(), labels=["ready_for_triage"], dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.owner == "owner"
    assert result.repo == "repo"
    assert result.repository == "owner/repo"
    assert result.issue_number == 42
    assert result.api_url == "https://api.github.test"
    assert result.endpoint == "https://api.github.test/repos/owner/repo/issues/42/labels"
    assert result.labels == [
        "max",
        "tact-spec",
        "idea",
        "triage-automation",
        "devtools",
        "approved",
        "recommendation:yes",
        "quality:needs-evidence",
        "team:agents",
        "ready-for-triage",
    ]
    assert result.payload["metadata"]["publisher"] == "max.github_issue_labels"
    assert result.payload["metadata"]["idea_id"] == "bu-label001"
    assert "secret" not in json.dumps(result.payload)


def test_build_design_brief_payload_maps_metadata_labels() -> None:
    publisher = GitHubIssueLabelsPublisher("owner/repo", issue_number=42)

    payload = publisher.build_design_brief_payload(
        _design_brief(),
        labels=["execution"],
    ).to_dict()

    assert payload["labels"] == [
        "max",
        "design-brief",
        "devtools",
        "triage-routing",
        "status:ready-for-build",
        "execution",
    ]
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-label001"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-support"]


def test_live_publish_posts_expected_github_labels_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {"name": "max"},
                {"name": "tact-spec"},
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssueLabelsPublisher(
        "owner/repo",
        issue_number=42,
        token="secret",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.endpoint == "https://api.github.com/repos/owner/repo/issues/42/labels"
    assert requests[0].url == "https://api.github.com/repos/owner/repo/issues/42/labels"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert requests[0].headers["User-Agent"] == "max-github-issue-labels-publisher/1"
    assert _json_from_request(requests[0]) == {"labels": result.labels}
    assert result.payload["metadata"]["github_issue_labels"] == result.labels


def test_publish_label_payload_allows_explicit_payload() -> None:
    publisher = GitHubIssueLabelsPublisher("owner/repo", labels=["default"])

    result = publisher.publish_label_payload(
        {
            "issue_number": "77",
            "labels": ["Design Review"],
            "metadata": {"source_type": "manual"},
        },
        dry_run=True,
    )

    assert result.issue_number == 77
    assert result.labels == ["design-review", "default"]
    assert result.payload["metadata"]["source_type"] == "manual"
    assert result.payload["metadata"]["repository"] == "owner/repo"


def test_live_publish_requires_token_before_http_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssueLabelsPublisher("owner/repo", issue_number=42, client=client)

    with pytest.raises(GitHubIssueLabelPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_error_redacts_sensitive_tokens_and_keeps_status_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text=(
                "bad token=body_secret password=body_password "
                "https://api.github.test/repos/owner/repo/issues/42/labels"
                "?token=url_secret&safe=yes"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubIssueLabelsPublisher(
        "owner/repo",
        issue_number=42,
        token="ghp_secret",
        api_url="https://api.github.test?token=site_secret",
        client=client,
    )

    with pytest.raises(GitHubIssueLabelPublishError, match="HTTP 403") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert exc.value.status_code == 403
    assert "body_secret" not in message
    assert "body_password" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "token=%3Credacted%3E" in message


def test_missing_issue_number_raises_clear_error() -> None:
    publisher = GitHubIssueLabelsPublisher("owner/repo")

    with pytest.raises(GitHubIssueLabelPublishError, match="issue number"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_from_env_reads_github_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_ISSUE_NUMBER", "123")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    publisher = GitHubIssueLabelsPublisher.from_env()

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.issue_number == 123
    assert publisher.token == "env-token"


def test_exported_from_publisher_package() -> None:
    assert ExportedGitHubIssueLabelsPublisher is GitHubIssueLabelsPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
