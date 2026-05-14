"""Tests for GitHub repository contributors import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_repository_contributors_adapter import GitHubRepositoryContributorsAdapter


CONTRIBUTOR = {
    "login": "octocat",
    "id": 1,
    "node_id": "MDQ6VXNlcjE=",
    "avatar_url": "https://avatars.github.example/u/1?v=4",
    "gravatar_id": "",
    "url": "https://api.github.example/users/octocat",
    "html_url": "https://github.example/octocat",
    "followers_url": "https://api.github.example/users/octocat/followers",
    "following_url": "https://api.github.example/users/octocat/following{/other_user}",
    "repos_url": "https://api.github.example/users/octocat/repos",
    "type": "User",
    "site_admin": False,
    "contributions": 42,
}


@pytest.mark.asyncio
async def test_github_repository_contributors_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[CONTRIBUTOR])
        return httpx.Response(200, json=[{**CONTRIBUTOR, "login": "hubot", "id": 2, "contributions": 7}])

    adapter = GitHubRepositoryContributorsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={"repository": "acme/api", "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    assert requests[0].headers["User-Agent"] == "max-github-repository-contributors-import/1"
    assert requests[0].url.path == "/api/v3/repos/acme/api/contributors"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[1].url.params["page"] == "2"

    signal = signals[0]
    assert signal.id == "github-repository-contributor:acme/api:1"
    assert signal.source_adapter == "github_repository_contributors_import"
    assert signal.title == "acme/api contributor octocat"
    assert signal.content == "GitHub contributor octocat for acme/api; 42 contributions"
    assert signal.url == "https://github.example/octocat"
    assert signal.author == "octocat"
    assert signal.metadata["repository"] == "acme/api"
    assert signal.metadata["repository_owner"] == "acme"
    assert signal.metadata["repository_name"] == "api"
    assert signal.metadata["login"] == "octocat"
    assert signal.metadata["contributions"] == 42
    assert signal.metadata["avatar_url"] == CONTRIBUTOR["avatar_url"]
    assert signal.metadata["html_url"] == CONTRIBUTOR["html_url"]
    assert signal.metadata["raw"] == CONTRIBUTOR


@pytest.mark.asyncio
async def test_github_repository_contributors_supports_multiple_config_object_repositories_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        repo_name = request.url.path.rsplit("/repos/", 1)[1].split("/contributors", 1)[0]
        return httpx.Response(200, json=[{**CONTRIBUTOR, "login": repo_name.replace("/", "-")}])

    adapter = GitHubRepositoryContributorsAdapter(
        token="gh-token",
        config={
            "repositories": [
                {"owner": "acme", "name": "api"},
                {"full_name": "acme/web"},
            ],
            "per_page": 100,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/repos/acme/api/contributors"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[1].url.path == "/repos/acme/web/contributors"
    assert requests[1].url.params["per_page"] == "1"
    assert [signal.metadata["repository"] for signal in signals] == ["acme/api", "acme/web"]


@pytest.mark.asyncio
async def test_github_repository_contributors_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_ACCESS_TOKEN", raising=False)

    assert await GitHubRepositoryContributorsAdapter(config={"repository": "acme/api"}).fetch() == []
    assert await GitHubRepositoryContributorsAdapter(token="token").fetch() == []
    assert await GitHubRepositoryContributorsAdapter(token="token", config={"repository": "acme/api"}).fetch(limit=0) == []

    failing = GitHubRepositoryContributorsAdapter(
        token="bad",
        config={"repository": "acme/api"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
