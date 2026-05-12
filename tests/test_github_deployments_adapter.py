"""Tests for GitHub deployments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_deployments_adapter import GitHubDeploymentsImportAdapter


DEPLOYMENT = {
    "id": 42,
    "sha": "abc123",
    "ref": "main",
    "task": "deploy",
    "environment": "production",
    "description": "Promote release candidate.",
    "payload": {"release": "2026.05.1", "change": "CHG-1"},
    "transient_environment": False,
    "production_environment": True,
    "original_environment": "prod",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:05:00Z",
    "url": "https://api.github.test/repos/acme/widgets/deployments/42",
    "html_url": "https://github.com/acme/widgets/deployments/42",
    "statuses_url": "https://api.github.test/repos/acme/widgets/deployments/42/statuses",
    "environment_url": "https://api.github.test/repos/acme/widgets/environments/production",
    "creator": {"login": "octocat", "id": 1, "html_url": "https://github.com/octocat"},
}


@pytest.mark.asyncio
async def test_github_deployments_fetch_filters_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[DEPLOYMENT])
        return httpx.Response(200, json=[{**DEPLOYMENT, "id": 43, "sha": "def456"}])

    adapter = GitHubDeploymentsImportAdapter(
        token="github_token",
        api_url="https://api.github.test",
        config={
            "repository": "acme/widgets",
            "sha": "abc123",
            "ref": "main",
            "task": "deploy",
            "environment": "production",
            "per_page": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/repos/acme/widgets/deployments"
    assert requests[0].url.params["sha"] == "abc123"
    assert requests[0].url.params["ref"] == "main"
    assert requests[0].url.params["task"] == "deploy"
    assert requests[0].url.params["environment"] == "production"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].headers["Authorization"] == "Bearer github_token"

    assert [signal.metadata["deployment_id"] for signal in signals] == [42, 43]
    signal = signals[0]
    assert signal.id == "github-deployment:acme/widgets:42"
    assert signal.source_adapter == "github_deployments_import"
    assert signal.source_type.value == "failure_data"
    assert signal.url == "https://github.com/acme/widgets/deployments/42"
    assert signal.author == "octocat"
    assert signal.metadata["repository"] == "acme/widgets"
    assert signal.metadata["sha"] == "abc123"
    assert signal.metadata["ref"] == "main"
    assert signal.metadata["task"] == "deploy"
    assert signal.metadata["environment"] == "production"
    assert signal.metadata["creator"]["login"] == "octocat"
    assert signal.metadata["payload"] == {"release": "2026.05.1", "change": "CHG-1"}
    assert signal.metadata["transient_environment"] is False
    assert signal.metadata["production_environment"] is True
    assert signal.metadata["original_environment"] == "prod"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-01T10:05:00Z"
    assert signal.metadata["deployment_url"] == "https://api.github.test/repos/acme/widgets/deployments/42"
    assert signal.metadata["signal_role"] == "release_readiness"


@pytest.mark.asyncio
async def test_github_deployments_supports_owner_repo_config_and_env_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[DEPLOYMENT])

    adapter = GitHubDeploymentsImportAdapter(
        api_url="https://api.github.test",
        config={"owner": "acme", "repo": "widgets"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.path == "/repos/acme/widgets/deployments"
    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["repository"] == "acme/widgets"


@pytest.mark.asyncio
async def test_github_deployments_supports_explicit_owner_repo_args() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[DEPLOYMENT])

    adapter = GitHubDeploymentsImportAdapter(
        token="token",
        api_url="https://api.github.test",
        owner="acme",
        repo="widgets",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.path == "/repos/acme/widgets/deployments"
    assert signals[0].metadata["deployment_id"] == 42


@pytest.mark.asyncio
async def test_github_deployments_empty_for_missing_config_bad_limits_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubDeploymentsImportAdapter(config={"repository": "acme/widgets"}).fetch() == []
    assert await GitHubDeploymentsImportAdapter(token="token").fetch() == []
    assert await GitHubDeploymentsImportAdapter(token="token", config={"repository": "acme/widgets"}).fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitHubDeploymentsImportAdapter(
        token="bad",
        config={"repository": "acme/widgets"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_github_deployments_malformed_payloads_are_skipped() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"sha": "missing-id"}, "bad"])

    adapter = GitHubDeploymentsImportAdapter(
        token="token",
        config={"repository": "acme/widgets"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
