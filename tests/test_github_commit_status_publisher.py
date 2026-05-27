from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.github_commit_statuses import GitHubCommitStatusPublishError, GitHubCommitStatusPublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_builds_github_commit_status_payload() -> None:
    publisher = GitHubCommitStatusPublisher(repository="acme/widgets", sha="abc123", context="max/readiness")

    result = publisher.publish(_tact_spec(), state="pending", target_url="https://max.example.test/specs/1", dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.endpoint == "https://api.github.com/repos/acme/widgets/statuses/abc123"
    assert result.payload["repository"] == "acme/widgets"
    assert result.payload["sha"] == "abc123"
    assert result.payload["status"]["context"] == "max/readiness"
    assert result.payload["status"]["state"] == "pending"
    assert result.payload["status"]["description"].startswith("Max TactSpec yes")
    assert result.payload["status"]["target_url"] == "https://max.example.test/specs/1"
    assert result.payload["metadata"]["publisher"] == "max.github_commit_statuses"
    assert result.payload["metadata"]["repository"] == "acme/widgets"


def test_live_publish_posts_github_commit_status() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 123, "url": "https://api.github.test/status/123"})

    publisher = GitHubCommitStatusPublisher(
        repository="acme/widgets",
        sha="abc123",
        token="gh_token",
        api_url="https://github.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), state="success", target_url="https://max.example.test/specs/1", description="TactSpec ready", dry_run=False)

    assert result.status_code == 201
    assert result.status_id == "123"
    assert result.status_url == "https://api.github.test/status/123"
    assert requests[0].url == "https://github.example.test/repos/acme/widgets/statuses/abc123"
    assert requests[0].headers["Authorization"] == "Bearer gh_token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    posted = json.loads(requests[0].read())
    assert posted == {"state": "success", "context": "max/tactspec-readiness", "description": "TactSpec ready", "target_url": "https://max.example.test/specs/1"}


def test_invalid_state_raises_publisher_error() -> None:
    publisher = GitHubCommitStatusPublisher(repository="acme/widgets", sha="abc123")

    with pytest.raises(GitHubCommitStatusPublishError, match="state must be one of"):
        publisher.publish(_tact_spec(), state="neutral", dry_run=True)


def test_live_publish_requires_github_token() -> None:
    publisher = GitHubCommitStatusPublisher(repository="acme/widgets", sha="abc123")

    with pytest.raises(GitHubCommitStatusPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_reads_github_commit_status_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env_token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "env/repo")
    monkeypatch.setenv("GITHUB_SHA", "env_sha")
    monkeypatch.setenv("GITHUB_STATUS_CONTEXT", "env/context")
    monkeypatch.setenv("GITHUB_API_URL", "https://github.env.test")

    publisher = GitHubCommitStatusPublisher.from_env()

    assert publisher.token == "env_token"
    assert publisher.repository == "env/repo"
    assert publisher.sha == "env_sha"
    assert publisher.context == "env/context"
    assert publisher.api_url == "https://github.env.test"
