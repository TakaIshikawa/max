"""Tests for Azure DevOps classic releases import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.azure_devops_releases_adapter import AzureDevOpsReleasesAdapter
from max.types.signal import SignalSourceType


RELEASE = {
    "id": 42,
    "name": "Release-42",
    "status": "active",
    "reason": "manual",
    "createdBy": {
        "displayName": "Ada Lovelace",
        "uniqueName": "ada@example.com",
        "id": "user-1",
        "imageUrl": "https://dev.azure.test/avatar/ada",
    },
    "createdOn": "2026-05-01T10:00:00Z",
    "releaseDefinition": {"id": 7, "name": "Production", "path": "\\", "url": "https://dev.azure.test/definition/7"},
    "environments": [
        {
            "id": 101,
            "name": "prod",
            "status": "succeeded",
            "rank": 1,
            "deploySteps": [{"id": 201, "status": "succeeded", "reason": "manual", "attempt": 1}],
        }
    ],
    "_links": {"web": {"href": "https://dev.azure.com/acme/max/_releaseProgress?releaseId=42"}},
    "url": "https://vsrm.dev.azure.test/acme/max/_apis/release/releases/42",
}


@pytest.mark.asyncio
async def test_azure_devops_releases_fetches_filters_auth_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"value": [RELEASE]})

    adapter = AzureDevOpsReleasesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        api_url="https://vsrm.dev.azure.test",
        config={
            "api_version": "7.0",
            "definition_id": 7,
            "status_filter": "active",
            "min_created_time": "2026-05-01T00:00:00Z",
            "max_created_time": "2026-05-02T00:00:00Z",
            "page_size": 25,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert requests[0].url.path == "/acme/max/_apis/release/releases"
    assert requests[0].url.params["api-version"] == "7.0"
    assert requests[0].url.params["definitionId"] == "7"
    assert requests[0].url.params["statusFilter"] == "active"
    assert requests[0].url.params["minCreatedTime"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["maxCreatedTime"] == "2026-05-02T00:00:00Z"
    assert requests[0].url.params["$top"] == "10"
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b":pat").decode()
    assert requests[0].headers["User-Agent"] == "max-azure-devops-releases-import/1"

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "azure-devops-release:42"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "azure_devops_releases_import"
    assert signal.title == "max release Release-42 active"
    assert signal.url == RELEASE["_links"]["web"]["href"]
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["signal_role"] == "solution"
    assert signal.metadata["organization"] == "acme"
    assert signal.metadata["project"] == "max"
    assert signal.metadata["release_id"] == 42
    assert signal.metadata["created_by"]["unique_name"] == "ada@example.com"
    assert signal.metadata["definition"]["name"] == "Production"
    assert signal.metadata["environments"][0]["deploy_steps"][0]["attempt"] == 1
    assert signal.metadata["raw"] == RELEASE


@pytest.mark.asyncio
async def test_azure_devops_releases_paginates_with_continuation_token_until_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"value": [{**RELEASE, "id": 1, "name": "Release-1"}]},
                headers={"x-ms-continuationtoken": "next-token"},
            )
        return httpx.Response(200, json={"value": [{**RELEASE, "id": 2, "name": "Release-2"}]})

    adapter = AzureDevOpsReleasesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"page_size": 1, "continuation_token": "start-token"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["$top"] for request in requests] == ["1", "1"]
    assert requests[0].url.params["continuationToken"] == "start-token"
    assert requests[1].url.params["continuationToken"] == "next-token"
    assert [signal.metadata["release_id"] for signal in signals] == [1, 2]


@pytest.mark.asyncio
async def test_azure_devops_releases_maps_failed_environment_as_failure_data() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"value": [{**RELEASE, "id": 43, "environments": [{**RELEASE["environments"][0], "status": "failed"}]}]},
        )

    adapter = AzureDevOpsReleasesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].source_type == SignalSourceType.FAILURE_DATA
    assert signals[0].metadata["signal_role"] == "problem"
    assert "failed environments prod" in signals[0].content


@pytest.mark.asyncio
async def test_azure_devops_releases_empty_without_required_config_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_DEVOPS_ORGANIZATION", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_TOKEN", raising=False)

    assert await AzureDevOpsReleasesAdapter(organization="acme", project="max").fetch() == []
    assert await AzureDevOpsReleasesAdapter(organization="acme", personal_access_token="pat").fetch() == []
    assert await AzureDevOpsReleasesAdapter(organization="acme", project="max", personal_access_token="pat").fetch(limit=0) == []

    empty = AzureDevOpsReleasesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"value": []}))),
    )
    assert await empty.fetch(limit=10) == []

    failing = AzureDevOpsReleasesAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=10) == []
