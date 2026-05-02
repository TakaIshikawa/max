"""Tests for GitHub repository topics publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    GitHubRepositoryTopicsPublisher as ExportedGitHubRepositoryTopicsPublisher,
)
from max.publisher.github_repository_topics import (
    GitHubRepositoryTopicPublishError,
    GitHubRepositoryTopicsPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "project": {
            "title": "Agent Triage SDK",
        },
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-topic001",
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
            "id": "dbf-topic001",
            "title": "Topics Design Brief",
            "domain": "devtools",
            "theme": "triage-routing",
            "lead_idea_id": "bu-lead",
            "source_idea_ids": ["bu-lead", "bu-support", "bu-lead"],
            "design_status": "ready_for_build",
        },
    }


def test_dry_run_returns_normalized_topics_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubRepositoryTopicsPublisher(
        "owner/repo",
        token="secret",
        api_url="https://api.github.test",
        topics=["Max", "Team Agents", "", "!!!"],
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        topics=["Ready_for_Triage", "Agent Triage SDK"],
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.status_code is None
    assert result.owner == "owner"
    assert result.repo == "repo"
    assert result.repository == "owner/repo"
    assert result.api_url == "https://api.github.test"
    assert result.endpoint == "https://api.github.test/repos/owner/repo/topics"
    assert result.topics == [
        "max",
        "tact-spec",
        "idea",
        "triage-automation",
        "devtools",
        "approved",
        "agent-triage-sdk",
        "yes",
        "needs-evidence",
        "team-agents",
        "ready-for-triage",
    ]
    assert result.payload["metadata"]["publisher"] == "max.github_repository_topics"
    assert result.payload["metadata"]["idea_id"] == "bu-topic001"
    assert "secret" not in json.dumps(result.payload)


def test_build_design_brief_payload_maps_metadata_topics() -> None:
    publisher = GitHubRepositoryTopicsPublisher("owner/repo")

    payload = publisher.build_design_brief_payload(
        _design_brief(),
        topics=["execution"],
    ).to_dict()

    assert payload["topics"] == [
        "max",
        "design-brief",
        "devtools",
        "triage-routing",
        "ready-for-build",
        "execution",
    ]
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-topic001"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-support"]


def test_live_publish_puts_expected_github_topics_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"names": ["max", "devtools"]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubRepositoryTopicsPublisher(
        "owner/repo",
        token="secret",
        client=client,
    )

    result = publisher.publish_topics(["Max", "DevTools"], dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.endpoint == "https://api.github.com/repos/owner/repo/topics"
    assert requests[0].method == "PUT"
    assert requests[0].url == "https://api.github.com/repos/owner/repo/topics"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert requests[0].headers["User-Agent"] == (
        "max-github-repository-topics-publisher/1"
    )
    assert _json_from_request(requests[0]) == {"names": result.topics}
    assert result.payload["metadata"]["github_repository_topics"] == result.topics


def test_publish_topic_payload_allows_explicit_payload() -> None:
    publisher = GitHubRepositoryTopicsPublisher("owner/repo", topics=["default"])

    result = publisher.publish_topic_payload(
        {
            "topics": ["Design Review", "!!!", "design-review"],
            "metadata": {"source_type": "manual"},
        },
        dry_run=True,
    )

    assert result.topics == ["design-review", "default"]
    assert result.payload["metadata"]["source_type"] == "manual"
    assert result.payload["metadata"]["repository"] == "owner/repo"


def test_publish_rejects_empty_topic_set_after_normalization() -> None:
    publisher = GitHubRepositoryTopicsPublisher("owner/repo")

    with pytest.raises(GitHubRepositoryTopicPublishError, match="At least one"):
        publisher.publish_topics(["", "!!!"], dry_run=True)


def test_publish_rejects_more_than_twenty_topics() -> None:
    publisher = GitHubRepositoryTopicsPublisher("owner/repo")

    with pytest.raises(GitHubRepositoryTopicPublishError, match="at most 20"):
        publisher.publish_topics([f"topic-{index}" for index in range(21)], dry_run=True)


def test_live_publish_requires_token_before_http_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubRepositoryTopicsPublisher("owner/repo", client=client)

    with pytest.raises(GitHubRepositoryTopicPublishError, match="GITHUB_TOKEN"):
        publisher.publish_topics(["max"], dry_run=False)


def test_live_publish_error_redacts_sensitive_tokens_and_keeps_status_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text=(
                "bad token=body_secret password=body_password "
                "https://api.github.test/repos/owner/repo/topics"
                "?token=url_secret&safe=yes"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubRepositoryTopicsPublisher(
        "owner/repo",
        token="ghp_secret",
        api_url="https://api.github.test?token=site_secret",
        client=client,
    )

    with pytest.raises(GitHubRepositoryTopicPublishError, match="HTTP 403") as exc:
        publisher.publish_topics(["max"], dry_run=False)

    message = str(exc.value)
    assert exc.value.status_code == 403
    assert "body_secret" not in message
    assert "body_password" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "token=%3Credacted%3E" in message


def test_from_env_reads_github_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    publisher = GitHubRepositoryTopicsPublisher.from_env()

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"


def test_exported_from_publisher_package() -> None:
    assert ExportedGitHubRepositoryTopicsPublisher is GitHubRepositoryTopicsPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
