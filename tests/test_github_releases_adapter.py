"""Tests for GitHub releases import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_releases_adapter import (
    GitHubReleasesAdapter,
    GitHubReleasesImportAdapter,
)


def _release(number: int, *, draft: bool = False, prerelease: bool = False) -> dict:
    return {
        "id": 1000 + number,
        "tag_name": f"v1.0.{number}",
        "name": f"Release {number}",
        "body": f"Release notes {number}",
        "draft": draft,
        "prerelease": prerelease,
        "target_commitish": "main",
        "created_at": "2026-05-01T10:00:00Z",
        "published_at": "2026-05-01T11:00:00Z",
        "html_url": f"https://github.com/acme/tool/releases/tag/v1.0.{number}",
        "upload_url": f"https://uploads.github.com/repos/acme/tool/releases/{1000 + number}/assets{{?name,label}}",
        "author": {
            "login": "maintainer",
            "id": 42,
            "html_url": "https://github.com/maintainer",
        },
        "assets": [{"id": 1}, {"id": 2}],
    }


@pytest.mark.asyncio
async def test_github_releases_paginates_across_repositories_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/repos/acme/tool/releases" and request.url.params["page"] == "1":
            return httpx.Response(200, json=[_release(1), _release(2, draft=True)])
        if request.url.path == "/repos/acme/tool/releases" and request.url.params["page"] == "2":
            return httpx.Response(200, json=[_release(3, prerelease=True)])
        return httpx.Response(200, json=[_release(4)])

    adapter = GitHubReleasesImportAdapter(
        token="gh-token",
        api_url="https://api.github.test",
        config={"repositories": ["acme/tool", "acme/other"], "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=4)

    assert GitHubReleasesAdapter is GitHubReleasesImportAdapter
    assert len(requests) == 3
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[1].url.params["page"] == "2"
    assert requests[2].url.path == "/repos/acme/other/releases"
    assert len(signals) == 4
    assert signals[0].id == "github-release:acme/tool:1001"
    assert signals[0].source_adapter == "github_releases_import"
    assert signals[0].source_type.value == "roadmap"
    assert signals[0].title == "Release 1"
    assert signals[0].content == "Release notes 1"
    assert signals[0].url == "https://github.com/acme/tool/releases/tag/v1.0.1"
    assert signals[0].author == "maintainer"
    assert signals[0].published_at is not None
    assert signals[0].metadata["github_release_id"] == 1001
    assert signals[0].metadata["repository"] == "acme/tool"
    assert signals[0].metadata["tag_name"] == "v1.0.1"
    assert signals[0].metadata["draft"] is False
    assert signals[0].metadata["prerelease"] is False
    assert signals[0].metadata["state"] == "published"
    assert signals[0].metadata["assets_count"] == 2
    assert signals[0].metadata["author"]["login"] == "maintainer"
    assert "release" in signals[0].tags


@pytest.mark.asyncio
async def test_github_releases_filters_state_and_accepts_repos_alias() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                _release(1),
                _release(2, draft=True),
                _release(3, prerelease=True),
            ],
        )

    adapter = GitHubReleasesImportAdapter(
        token="gh-token",
        config={"repos": "acme/tool", "state": "prerelease"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert [signal.metadata["tag_name"] for signal in signals] == ["v1.0.3"]
    assert signals[0].metadata["state"] == "prerelease"


@pytest.mark.asyncio
async def test_github_releases_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert await GitHubReleasesImportAdapter(config={"repositories": ["acme/tool"]}).fetch() == []
    assert await GitHubReleasesImportAdapter(token="token").fetch() == []
    assert await GitHubReleasesImportAdapter(token="token", config={"repositories": ["acme/tool"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_github_releases_reads_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_release(1)])

    adapter = GitHubReleasesImportAdapter(
        config={"repositories": ["acme/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["repository"] == "acme/tool"


@pytest.mark.asyncio
async def test_github_releases_api_or_non_json_failure_returns_empty() -> None:
    failing = GitHubReleasesImportAdapter(
        token="gh-token",
        config={"repositories": ["acme/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = GitHubReleasesImportAdapter(
        token="gh-token",
        config={"repositories": ["acme/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not json"))),
    )
    assert await non_json.fetch(limit=2) == []
