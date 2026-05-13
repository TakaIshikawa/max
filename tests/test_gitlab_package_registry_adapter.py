"""Tests for GitLab package registry import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_package_registry_adapter import (
    GitLabPackageRegistryAdapter,
    GitLabPackageRegistryImportAdapter,
)


def _package(number: int, *, package_type: str = "maven", status: str = "default") -> dict:
    return {
        "id": 8000 + number,
        "name": f"agent-sdk-{number}",
        "version": f"1.0.{number}",
        "package_type": package_type,
        "status": status,
        "created_at": "2026-05-01T10:00:00.000Z",
        "updated_at": "2026-05-01T11:00:00.000Z",
        "project_id": 278964,
        "web_url": f"https://gitlab.example/group/tool/-/packages/{8000 + number}",
        "pipeline": {
            "id": 101 + number,
            "iid": 7 + number,
            "status": "success",
            "ref": "main",
            "sha": f"abc{number}",
            "web_url": f"https://gitlab.example/group/tool/-/pipelines/{101 + number}",
        },
        "creator_id": 42,
    }


@pytest.mark.asyncio
async def test_gitlab_package_registry_fetches_encoded_project_paths_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_package(1)])

    adapter = GitLabPackageRegistryImportAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={"projects": ["group/sub/tool"], "per_page": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert GitLabPackageRegistryAdapter is GitLabPackageRegistryImportAdapter
    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert str(requests[0].url).startswith(
        "https://gitlab.example/api/v4/projects/group%2Fsub%2Ftool/packages"
    )
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"

    signal = signals[0]
    assert signal.id == "gitlab-package:group/sub/tool:8001:1.0.1"
    assert signal.source_adapter == "gitlab_package_registry_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "group/sub/tool agent-sdk-1 1.0.1"
    assert signal.url == "https://gitlab.example/group/tool/-/packages/8001"
    assert signal.author == "42"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "readiness"
    assert signal.metadata["project_id"] == 278964
    assert signal.metadata["project_path"] == "group/sub/tool"
    assert signal.metadata["package_id"] == 8001
    assert signal.metadata["name"] == "agent-sdk-1"
    assert signal.metadata["version"] == "1.0.1"
    assert signal.metadata["package_type"] == "maven"
    assert signal.metadata["status"] == "default"
    assert signal.metadata["pipeline"]["id"] == 102
    assert signal.metadata["pipeline"]["status"] == "success"
    assert signal.metadata["raw"]["id"] == 8001
    assert {"gitlab", "package", "maven", "default"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_gitlab_package_registry_paginates_across_projects_with_limits() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        if raw_path.endswith("/group%2Ftool/packages") and request.url.params["page"] == "1":
            return httpx.Response(200, json=[_package(1)])
        if raw_path.endswith("/group%2Ftool/packages") and request.url.params["page"] == "2":
            return httpx.Response(200, json=[_package(2)])
        return httpx.Response(200, json=[_package(3)])

    adapter = GitLabPackageRegistryImportAdapter(
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
    assert requests[2].url.path == "/api/v4/projects/278964/packages"
    assert [signal.metadata["package_id"] for signal in signals] == [8001, 8002, 8003]


@pytest.mark.asyncio
async def test_gitlab_package_registry_sends_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_package(1, package_type="npm", status="processing")])

    adapter = GitLabPackageRegistryImportAdapter(
        token="gitlab-token",
        config={
            "project_ids": "group/tool",
            "base_url": "https://gitlab.example",
            "package_type": "npm",
            "status": "processing",
            "order_by": "created_at",
            "sort": "asc",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=1)

    assert requests[0].url.params["package_type"] == "npm"
    assert requests[0].url.params["status"] == "processing"
    assert requests[0].url.params["order_by"] == "created_at"
    assert requests[0].url.params["sort"] == "asc"


@pytest.mark.asyncio
async def test_gitlab_package_registry_reads_env_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "private-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_package(1)])

    adapter = GitLabPackageRegistryImportAdapter(
        config={"projects": ["group/tool"], "gitlab_url": "https://gitlab.example"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["PRIVATE-TOKEN"] == "private-token"
    assert signals[0].metadata["project_path"] == "group/tool"


@pytest.mark.asyncio
async def test_gitlab_package_registry_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabPackageRegistryImportAdapter(config={"projects": ["group/tool"]}).fetch() == []
    assert await GitLabPackageRegistryImportAdapter(token="token").fetch() == []
    assert (
        await GitLabPackageRegistryImportAdapter(token="token", config={"projects": ["group/tool"]}).fetch(limit=0)
        == []
    )


@pytest.mark.asyncio
async def test_gitlab_package_registry_http_or_non_json_failure_returns_empty() -> None:
    failing = GitLabPackageRegistryImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = GitLabPackageRegistryImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
