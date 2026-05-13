"""Tests for GitHub repository environments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_repository_environments_adapter import (
    GitHubRepositoryEnvironmentsAdapter,
    GitHubRepositoryEnvironmentsImportAdapter,
)


ENVIRONMENT = {
    "id": 161088068,
    "node_id": "EN_kwDOABC1234AAA",
    "name": "production",
    "url": "https://api.github.test/repos/acme/widgets/environments/production",
    "html_url": "https://github.com/acme/widgets/deployments/activity_log?environments_filter=production",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T10:00:00Z",
    "protection_rules": [
        {
            "id": 1,
            "type": "required_reviewers",
            "prevent_self_review": True,
            "reviewers": [
                {
                    "type": "User",
                    "reviewer": {"id": 42, "login": "octocat", "html_url": "https://github.com/octocat"},
                }
            ],
        },
        {"id": 2, "type": "wait_timer", "wait_timer": 30},
    ],
    "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
}


@pytest.mark.asyncio
async def test_github_repository_environments_paginates_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "total_count": 3,
                    "environments": [
                        {**ENVIRONMENT, "id": 161088068, "name": "production"},
                        {**ENVIRONMENT, "id": 161088069, "name": "staging"},
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "total_count": 3,
                "environments": [{**ENVIRONMENT, "id": 161088070, "name": "production"}],
            },
        )

    adapter = GitHubRepositoryEnvironmentsImportAdapter(
        token="github_token",
        api_url="https://api.github.test",
        config={"repository": "acme/widgets", "environment": "production", "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert GitHubRepositoryEnvironmentsAdapter is GitHubRepositoryEnvironmentsImportAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/repos/acme/widgets/environments"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].headers["Authorization"] == "Bearer github_token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    assert requests[0].headers["X-GitHub-Api-Version"] == "2022-11-28"

    assert [signal.metadata["environment_id"] for signal in signals] == [161088068, 161088070]
    signal = signals[0]
    assert signal.id == "github-repository-environment:acme/widgets:161088068"
    assert signal.source_adapter == "github_repository_environments_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "acme/widgets environment production"
    assert signal.url == "https://github.com/acme/widgets/deployments/activity_log?environments_filter=production"
    assert signal.metadata["signal_role"] == "release_readiness"
    assert signal.metadata["repository"] == "acme/widgets"
    assert signal.metadata["name"] == "production"
    assert signal.metadata["protection_rules"][0]["type"] == "required_reviewers"
    assert signal.metadata["protection_rules"][0]["reviewers"][0]["login"] == "octocat"
    assert signal.metadata["protection_rules"][1]["wait_timer"] == 30
    assert signal.metadata["deployment_branch_policy"] == {
        "protected_branches": True,
        "custom_branch_policies": False,
    }
    assert signal.metadata["raw"]["id"] == 161088068
    assert "deployment-gate" in signal.tags
    assert "required_reviewers" in signal.tags


@pytest.mark.asyncio
async def test_github_repository_environments_encodes_repository_path_and_respects_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "total_count": 2,
                "environments": [
                    {**ENVIRONMENT, "id": 1, "name": "qa"},
                    {**ENVIRONMENT, "id": 2, "name": "prod"},
                ],
            },
        )

    adapter = GitHubRepositoryEnvironmentsImportAdapter(
        token="github_token",
        base_url="https://github.enterprise/api/v3",
        config={"repositories": ["acme tools/space repo"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v3/repos/acme%20tools/space%20repo/environments"
    assert str(requests[0].url).startswith("https://github.enterprise/api/v3/")
    assert requests[0].url.params["per_page"] == "1"
    assert [signal.metadata["environment_id"] for signal in signals] == [1]


@pytest.mark.asyncio
async def test_github_repository_environments_uses_config_and_env_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"total_count": 1, "environments": [ENVIRONMENT]})

    adapter = GitHubRepositoryEnvironmentsImportAdapter(
        config={"base_url": "https://api.github.test"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.path == "/repos/env-owner/env-repo/environments"
    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["repository"] == "env-owner/env-repo"


@pytest.mark.asyncio
async def test_github_repository_environments_supports_owner_repo_config() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"total_count": 1, "environments": [ENVIRONMENT]})

    adapter = GitHubRepositoryEnvironmentsImportAdapter(
        token="token",
        api_url="https://api.github.test",
        config={"owner": "acme", "repo": "widgets"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.path == "/repos/acme/widgets/environments"
    assert signals[0].metadata["environment_id"] == 161088068


@pytest.mark.asyncio
async def test_github_repository_environments_empty_without_token_repository_or_positive_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert await GitHubRepositoryEnvironmentsImportAdapter(config={"repository": "acme/widgets"}).fetch() == []
    assert await GitHubRepositoryEnvironmentsImportAdapter(token="token").fetch() == []
    assert (
        await GitHubRepositoryEnvironmentsImportAdapter(
            token="token",
            config={"repository": "acme/widgets"},
        ).fetch(limit=0)
        == []
    )


@pytest.mark.asyncio
async def test_github_repository_environments_http_and_non_json_failures_return_empty() -> None:
    async def http_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    http_error_adapter = GitHubRepositoryEnvironmentsImportAdapter(
        token="bad",
        config={"repository": "acme/widgets"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(http_error_handler)),
    )
    assert await http_error_adapter.fetch(limit=10) == []

    async def non_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    non_json_adapter = GitHubRepositoryEnvironmentsImportAdapter(
        token="bad",
        config={"repository": "acme/widgets"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(non_json_handler)),
    )
    assert await non_json_adapter.fetch(limit=10) == []
