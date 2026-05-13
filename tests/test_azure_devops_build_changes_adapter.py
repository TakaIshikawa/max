"""Tests for Azure DevOps build changes import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.azure_devops_build_changes_adapter import AzureDevOpsBuildChangesAdapter
from max.types.signal import SignalSourceType


def _change(change_id: str, *, message: str = "Update deployment manifest") -> dict:
    return {
        "id": change_id,
        "message": message,
        "type": "TfsGit",
        "author": {
            "displayName": "Ada Lovelace",
            "uniqueName": "ada@example.com",
            "id": "user-1",
        },
        "timestamp": "2026-05-01T10:00:00Z",
        "location": f"https://dev.azure.com/acme/max/_git/max/commit/{change_id}",
    }


@pytest.mark.asyncio
async def test_azure_devops_build_changes_fetches_pages_and_maps_changes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"value": [_change("abc"), _change("abc")]},
                headers={"x-ms-continuationtoken": "next-page"},
            )
        return httpx.Response(200, json={"value": [_change("def", message="Fix tests")]})

    adapter = AzureDevOpsBuildChangesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        api_url="https://dev.azure.test",
        config={"build_id": 101, "api_version": "7.0", "page_size": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert len(requests) == 2
    assert requests[0].url.path == "/acme/max/_apis/build/builds/101/changes"
    assert requests[0].url.params["api-version"] == "7.0"
    assert requests[0].url.params["$top"] == "2"
    assert "continuationToken" not in requests[0].url.params
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b":pat").decode()
    assert requests[1].url.params["continuationToken"] == "next-page"
    assert [signal.metadata["change_id"] for signal in signals] == ["abc", "def"]

    signal = signals[0]
    assert signal.id == "azure-devops-build-change:acme/max:101:abc"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "azure_devops_build_changes_import"
    assert signal.title == "max build 101 change abc"
    assert signal.content == "Update deployment manifest"
    assert signal.url == "https://dev.azure.com/acme/max/_git/max/commit/abc"
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["organization"] == "acme"
    assert signal.metadata["project"] == "max"
    assert signal.metadata["build_id"] == "101"
    assert signal.metadata["type"] == "TfsGit"
    assert signal.metadata["author"]["uniqueName"] == "ada@example.com"
    assert signal.metadata["timestamp"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["location"] == "https://dev.azure.com/acme/max/_git/max/commit/abc"
    assert signal.metadata["raw"]["id"] == "abc"
    assert "build-change" in signal.tags


@pytest.mark.asyncio
async def test_azure_devops_build_changes_fetches_multiple_builds_with_limits() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        build_id = request.url.path.split("/builds/", 1)[1].split("/", 1)[0]
        return httpx.Response(
            200,
            json={"value": [_change(f"{build_id}-one"), _change(f"{build_id}-two")]},
        )

    adapter = AzureDevOpsBuildChangesAdapter(
        organization="acme",
        project="max",
        token="pat",
        config={"build_ids": [101, 102], "per_build_limit": 1, "page_size": 10},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.params["$top"] == "1"
    assert [signal.metadata["build_id"] for signal in signals] == ["101", "102"]
    assert [signal.metadata["change_id"] for signal in signals] == ["101-one", "102-one"]


@pytest.mark.asyncio
async def test_azure_devops_build_changes_uses_env_pat_and_config() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"value": [_change("abc")]})

    adapter = AzureDevOpsBuildChangesAdapter(
        config={
            "organization": "env-org",
            "project": "env-project",
            "build_ids": "201,202",
            "pat": "config-pat",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].url.path == "/env-org/env-project/_apis/build/builds/201/changes"
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b":config-pat").decode()


@pytest.mark.asyncio
async def test_azure_devops_build_changes_missing_config_or_failure_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DEVOPS_ORGANIZATION", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_TOKEN", raising=False)

    assert await AzureDevOpsBuildChangesAdapter(
        organization="acme",
        project="max",
        config={"build_ids": [101]},
    ).fetch() == []
    assert await AzureDevOpsBuildChangesAdapter(
        organization="acme",
        personal_access_token="pat",
        config={"build_ids": [101]},
    ).fetch() == []
    assert await AzureDevOpsBuildChangesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
    ).fetch() == []
    assert await AzureDevOpsBuildChangesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"build_ids": [101]},
    ).fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = AzureDevOpsBuildChangesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"build_ids": [101]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
