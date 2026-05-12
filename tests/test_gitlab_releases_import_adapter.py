"""Tests for GitLab releases import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_releases_adapter import (
    GitLabReleasesAdapter,
    GitLabReleasesImportAdapter,
)


def _release(number: int, *, tag_name: str | None = None) -> dict:
    return {
        "name": f"Release {number}",
        "tag_name": tag_name or f"v1.0.{number}",
        "description": f"Release notes {number}",
        "released_at": "2026-05-01T10:00:00.000Z",
        "created_at": "2026-04-30T10:00:00.000Z",
        "project_id": 278964,
        "_links": {"self": f"https://gitlab.example/group/tool/-/releases/v1.0.{number}"},
        "author": {
            "id": 42,
            "username": "maintainer",
            "name": "Maintainer",
            "web_url": "https://gitlab.example/maintainer",
        },
        "commit": {
            "id": f"abc{number}",
            "short_id": f"abc{number}",
            "title": "Release commit",
            "web_url": f"https://gitlab.example/group/tool/-/commit/abc{number}",
        },
        "milestones": [{"title": "1.0"}],
        "assets": {
            "links": [{"name": "binary", "url": "https://gitlab.example/download"}],
            "sources": [{"format": "zip"}],
        },
    }


@pytest.mark.asyncio
async def test_gitlab_releases_fetches_encoded_project_paths_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_release(1)])

    adapter = GitLabReleasesImportAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={"projects": ["group/sub/tool"], "per_page": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert GitLabReleasesAdapter is GitLabReleasesImportAdapter
    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert str(requests[0].url).startswith(
        "https://gitlab.example/api/v4/projects/group%2Fsub%2Ftool/releases"
    )
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"

    signal = signals[0]
    assert signal.id == "gitlab-release:group/sub/tool:v1.0.1"
    assert signal.source_adapter == "gitlab_releases_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "group/sub/tool Release 1 (v1.0.1)"
    assert signal.content == "Release notes 1"
    assert signal.url == "https://gitlab.example/group/tool/-/releases/v1.0.1"
    assert signal.author == "maintainer"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "readiness"
    assert signal.metadata["project_id"] == 278964
    assert signal.metadata["project_path"] == "group/sub/tool"
    assert signal.metadata["tag_name"] == "v1.0.1"
    assert signal.metadata["author"]["username"] == "maintainer"
    assert signal.metadata["commit"]["id"] == "abc1"
    assert signal.metadata["commit_path"] == "https://gitlab.example/group/tool/-/commit/abc1"
    assert signal.metadata["milestones"] == ["1.0"]
    assert signal.metadata["assets_links"][0]["name"] == "binary"
    assert signal.metadata["assets_count"] == 2
    assert {"gitlab", "release", "v1.0.1"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_gitlab_releases_paginates_across_projects_with_limits() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        if raw_path.endswith("/group%2Ftool/releases") and request.url.params["page"] == "1":
            return httpx.Response(200, json=[_release(1)])
        if raw_path.endswith("/group%2Ftool/releases") and request.url.params["page"] == "2":
            return httpx.Response(200, json=[_release(2)])
        return httpx.Response(200, json=[_release(3)])

    adapter = GitLabReleasesImportAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example",
        config={
            "projects": ["group/tool", "278964"],
            "per_page": 1,
            "per_project_limit": 2,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [request.url.params["page"] for request in requests] == ["1", "2", "1"]
    assert requests[2].url.path == "/api/v4/projects/278964/releases"
    assert [signal.metadata["tag_name"] for signal in signals] == ["v1.0.1", "v1.0.2", "v1.0.3"]


@pytest.mark.asyncio
async def test_gitlab_releases_sends_date_and_sort_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_release(1)])

    adapter = GitLabReleasesImportAdapter(
        token="gitlab-token",
        config={
            "project_ids": "group/tool",
            "base_url": "https://gitlab.example",
            "released_after": "2026-05-01T00:00:00Z",
            "released_before": "2026-05-31T00:00:00Z",
            "order_by": "released_at",
            "sort": "asc",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=1)

    assert requests[0].url.params["released_after"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["released_before"] == "2026-05-31T00:00:00Z"
    assert requests[0].url.params["order_by"] == "released_at"
    assert requests[0].url.params["sort"] == "asc"


@pytest.mark.asyncio
async def test_gitlab_releases_reads_env_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "private-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_release(1)])

    adapter = GitLabReleasesImportAdapter(
        config={"projects": ["group/tool"], "gitlab_url": "https://gitlab.example"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["PRIVATE-TOKEN"] == "private-token"
    assert signals[0].metadata["project_path"] == "group/tool"


@pytest.mark.asyncio
async def test_gitlab_releases_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabReleasesImportAdapter(config={"projects": ["group/tool"]}).fetch() == []
    assert await GitLabReleasesImportAdapter(token="token").fetch() == []
    assert await GitLabReleasesImportAdapter(token="token", config={"projects": ["group/tool"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_releases_http_or_non_json_failure_returns_empty() -> None:
    failing = GitLabReleasesImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = GitLabReleasesImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
