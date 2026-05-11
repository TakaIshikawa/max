"""Tests for GitHub pull request publisher."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.github_pull_requests import GitHubPullRequestPublishError, GitHubPullRequestPublisher
from max.types.buildable_unit import BuildableUnit


def _unit() -> BuildableUnit:
    return BuildableUnit(title="PR Idea", one_liner="Open a PR", category="integration", problem="Manual handoff", solution="Publish PR", value_proposition="Faster handoff", id="bu-1", domain="devtools", status="approved")


def test_build_payload_from_buildable_unit() -> None:
    publisher = GitHubPullRequestPublisher("acme/app", base="main", head="feature/max-pr", labels=["ready"])
    payload = publisher.build_payload(_unit()).to_dict()

    assert payload["title"] == "[Max] PR Idea"
    assert payload["base"] == "main"
    assert payload["head"] == "feature/max-pr"
    assert payload["draft"] is False
    assert payload["maintainer_can_modify"] is True
    assert "integration" in payload["labels"]
    assert payload["metadata"]["idea_id"] == "bu-1"


def test_dry_run_returns_payload_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not call GitHub")

    publisher = GitHubPullRequestPublisher("acme/app", head="feature/max-pr", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = publisher.publish(_unit(), dry_run=True)

    assert result.dry_run is True
    assert result.pull_request_number is None
    assert result.payload["head"] == "feature/max-pr"


def test_live_publish_posts_pull_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"number": 42, "html_url": "https://github.test/acme/app/pull/42"})

    publisher = GitHubPullRequestPublisher("acme/app", token="gh_secret", api_url="https://api.github.test", head="feature/max-pr", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = publisher.publish(_unit(), dry_run=False)

    assert result.status_code == 201
    assert result.pull_request_number == 42
    assert result.pull_request_url == "https://github.test/acme/app/pull/42"
    assert requests[0].url == "https://api.github.test/repos/acme/app/pulls"
    posted = json.loads(requests[0].read())
    assert posted["head"] == "feature/max-pr"
    assert posted["base"] == "main"


def test_live_publish_requires_token_and_redacts_errors() -> None:
    publisher = GitHubPullRequestPublisher("acme/app", head="feature/max-pr")
    with pytest.raises(GitHubPullRequestPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_unit(), dry_run=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "bad gh_secret"})

    publisher = GitHubPullRequestPublisher("acme/app", token="gh_secret", head="feature/max-pr", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(GitHubPullRequestPublishError) as exc:
        publisher.publish(_unit(), dry_run=False)
    assert "gh_secret" not in str(exc.value)


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_PR_BASE", "develop")
    monkeypatch.setenv("GITHUB_PR_HEAD", "feature/env")
    monkeypatch.setenv("GITHUB_PR_DRAFT", "true")

    publisher = GitHubPullRequestPublisher.from_env()

    assert publisher.token == "env-token"
    assert publisher.repository == "acme/app"
    assert publisher.base == "develop"
    assert publisher.head == "feature/env"
    assert publisher.draft is True
