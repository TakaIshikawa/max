from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.github_deployment_statuses import GitHubDeploymentStatusPublishError, GitHubDeploymentStatusPublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_deployment_status_payload() -> None:
    publisher = GitHubDeploymentStatusPublisher(repository="acme/widgets", deployment_id="42", environment="staging", log_url="https://logs.example.test/42")

    payload = publisher.build_status_payload(_unit(), state="in_progress")

    assert payload["state"] == "in_progress"
    assert payload["environment"] == "staging"
    assert payload["log_url"] == "https://logs.example.test/42"
    assert payload["context"] == "max/bu-stripe001"
    assert "Stripe Customer Note Publisher" in payload["description"]
    assert payload["metadata"]["publisher"] == "max.github_deployment_statuses"


def test_from_env_reads_github_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    monkeypatch.setenv("GITHUB_DEPLOYMENT_ID", "42")
    monkeypatch.setenv("GITHUB_API_URL", "https://github.example.test")
    monkeypatch.setenv("GITHUB_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("GITHUB_DEPLOYMENT_LOG_URL", "https://logs.example.test/42")

    publisher = GitHubDeploymentStatusPublisher.from_env(max_retries=3)

    assert publisher.token == "env-token"
    assert publisher.repository == "acme/widgets"
    assert publisher.deployment_id == "42"
    assert publisher.api_url == "https://github.example.test"
    assert publisher.environment == "staging"
    assert publisher.log_url == "https://logs.example.test/42"
    assert publisher.max_retries == 3


def test_invalid_state_fails_before_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid state should not make network calls")

    publisher = GitHubDeploymentStatusPublisher(repository="acme/widgets", deployment_id="42", client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(GitHubDeploymentStatusPublishError, match="state must be one of"):
        publisher.publish(_unit(), state="done", dry_run=False)


def test_dry_run_exposes_endpoint_and_payload() -> None:
    publisher = GitHubDeploymentStatusPublisher(repository="acme/widgets", deployment_id="42", api_url="https://github.example.test")

    result = publisher.publish(_unit(), state="queued", dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://github.example.test/repos/acme/widgets/deployments/42/statuses"
    assert result.payload["state"] == "queued"


def test_live_publish_posts_status_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 99, "url": "https://api.github.test/statuses/99"})

    publisher = GitHubDeploymentStatusPublisher(token="gh-token", repository="acme/widgets", deployment_id="42", api_url="https://github.example.test", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_unit(), state="success", dry_run=False)

    assert result.deployment_status_id == "99"
    assert result.deployment_status_url == "https://api.github.test/statuses/99"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    posted = json.loads(requests[0].read())
    assert posted["state"] == "success"
    assert "metadata" not in posted


def test_missing_token_and_retry_redaction() -> None:
    publisher = GitHubDeploymentStatusPublisher(repository="acme/widgets", deployment_id="42")

    with pytest.raises(GitHubDeploymentStatusPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_unit(), dry_run=False)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="bad Bearer gh-token")

    retrying = GitHubDeploymentStatusPublisher(token="gh-token", repository="acme/widgets", deployment_id="42", max_retries=1, client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(GitHubDeploymentStatusPublishError) as exc:
        retrying.publish(_unit(), dry_run=False)

    assert calls == 2
    assert "gh-token" not in str(exc.value)
