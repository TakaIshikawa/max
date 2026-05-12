"""Tests for Azure DevOps build timeline import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.azure_devops_build_timeline_adapter import AzureDevOpsBuildTimelineAdapter
from max.types.signal import SignalSourceType


FAILED_RECORD = {
    "id": "record-1",
    "parentId": "parent-1",
    "type": "Task",
    "name": "pytest",
    "state": "completed",
    "result": "failed",
    "workerName": "agent-1",
    "order": 3,
    "startTime": "2026-05-01T10:00:00Z",
    "finishTime": "2026-05-01T10:02:30Z",
    "log": {"id": 12, "type": "Container", "url": "https://dev.azure.com/acme/max/_apis/build/builds/101/logs/12"},
    "issues": [{"type": "error", "category": "Build", "message": "Tests failed"}],
}


@pytest.mark.asyncio
async def test_azure_devops_build_timeline_fetches_and_maps_records() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"records": [FAILED_RECORD]})

    adapter = AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        api_url="https://dev.azure.test",
        config={"build_ids": [101], "api_version": "7.0"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].url.path == "/acme/max/_apis/build/builds/101/timeline"
    assert requests[0].url.params["api-version"] == "7.0"
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b":pat").decode()
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "azure-devops-build-timeline:acme/max:101:record-1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "azure_devops_build_timeline_import"
    assert signal.title == "max build 101 pytest failed"
    assert signal.content == "Tests failed"
    assert signal.url == FAILED_RECORD["log"]["url"]
    assert signal.metadata["organization"] == "acme"
    assert signal.metadata["project"] == "max"
    assert signal.metadata["build_id"] == "101"
    assert signal.metadata["record_id"] == "record-1"
    assert signal.metadata["parent_id"] == "parent-1"
    assert signal.metadata["type"] == "Task"
    assert signal.metadata["worker_name"] == "agent-1"
    assert signal.metadata["duration_seconds"] == 150
    assert signal.metadata["log"]["id"] == 12
    assert signal.metadata["issues"][0]["message"] == "Tests failed"
    assert signal.metadata["raw"] == FAILED_RECORD
    assert "build-timeline" in signal.tags


@pytest.mark.asyncio
async def test_azure_devops_build_timeline_filters_successful_unless_configured() -> None:
    records = [
        {**FAILED_RECORD, "id": "successful", "result": "succeeded", "issues": []},
        {**FAILED_RECORD, "id": "warning", "result": "succeeded", "issues": [{"type": "warning", "message": "Slow tests"}]},
        {**FAILED_RECORD, "id": "running", "state": "inProgress", "result": None, "issues": []},
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"records": records})

    adapter = AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"build_ids": [101]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=10)
    assert [signal.metadata["record_id"] for signal in signals] == ["warning", "running"]

    include_adapter = AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"build_ids": [101], "include_successful": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    include_signals = await include_adapter.fetch(limit=10)
    assert [signal.metadata["record_id"] for signal in include_signals] == ["successful", "warning", "running"]


@pytest.mark.asyncio
async def test_azure_devops_build_timeline_respects_record_types_and_limits_across_builds() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        build_id = request.url.path.split("/builds/", 1)[1].split("/", 1)[0]
        return httpx.Response(
            200,
            json={
                "records": [
                    {**FAILED_RECORD, "id": f"{build_id}-job", "type": "Job", "name": "build job"},
                    {**FAILED_RECORD, "id": f"{build_id}-task", "type": "Task", "name": "build task"},
                ]
            },
        )

    adapter = AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"build_ids": [101, 102], "record_types": ["Task"], "per_build_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert [signal.metadata["build_id"] for signal in signals] == ["101", "102"]
    assert [signal.metadata["type"] for signal in signals] == ["Task", "Task"]


@pytest.mark.asyncio
async def test_azure_devops_build_timeline_missing_config_or_failure_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DEVOPS_ORGANIZATION", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_TOKEN", raising=False)

    assert await AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        config={"build_ids": [101]},
    ).fetch() == []
    assert await AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        personal_access_token="pat",
        config={"build_ids": [101]},
    ).fetch() == []
    assert await AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
    ).fetch() == []
    assert await AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"build_ids": [101]},
    ).fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = AzureDevOpsBuildTimelineAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"build_ids": [101]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
