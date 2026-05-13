"""Tests for CircleCI job artifacts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.circleci_job_artifacts_adapter import CircleCIJobArtifactsImportAdapter
from max.types.signal import SignalSourceType


ARTIFACT = {
    "path": "coverage/index.html",
    "node_index": 0,
    "url": "https://circleci.example/artifacts/coverage/index.html",
    "branch": "main",
    "build_num": 101,
    "build_url": "https://app.circleci.com/pipelines/github/example/tool/42/workflows/wf/jobs/101",
    "workflow_id": "wf-1",
    "job_name": "test",
    "created_at": "2026-05-01T10:03:00Z",
}


@pytest.mark.asyncio
async def test_circleci_job_artifacts_fetches_and_maps_artifacts() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [ARTIFACT]})

    adapter = CircleCIJobArtifactsImportAdapter(
        token="circle-token",
        api_url="https://circleci.test/api/v2",
        config={"project_slug": "gh/example/tool", "job_numbers": [101], "page_size": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].url.path == "/api/v2/project/gh/example/tool/101/artifacts"
    assert requests[0].url.params["page-size"] == "25"
    assert requests[0].headers["Circle-Token"] == "circle-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "circleci-artifact:gh/example/tool:101:0:coverage/index.html"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "circleci_job_artifacts_import"
    assert signal.title == "gh/example/tool job #101 artifact: coverage/index.html"
    assert signal.url == ARTIFACT["url"]
    assert signal.metadata["artifact_path"] == "coverage/index.html"
    assert signal.metadata["node_index"] == 0
    assert signal.metadata["url"] == ARTIFACT["url"]
    assert signal.metadata["job_number"] == "101"
    assert signal.metadata["project_slug"] == "gh/example/tool"
    assert signal.metadata["branch"] == "main"
    assert signal.metadata["build_number"] == 101
    assert signal.metadata["raw"] == ARTIFACT
    assert "artifact" in signal.tags


@pytest.mark.asyncio
async def test_circleci_job_artifacts_paginates_and_honors_global_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "page-token" not in request.url.params:
            return httpx.Response(
                200,
                json={"items": [{**ARTIFACT, "path": "a.txt"}], "next_page_token": "next"},
            )
        return httpx.Response(200, json={"items": [{**ARTIFACT, "path": "b.txt"}]})

    adapter = CircleCIJobArtifactsImportAdapter(
        token="circle-token",
        config={"project_slug": "gh/example/tool", "job_number": 101, "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["artifact_path"] for signal in signals] == ["a.txt", "b.txt"]
    assert requests[1].url.params["page-token"] == "next"
    assert [request.url.params["page-size"] for request in requests] == ["1", "1"]


@pytest.mark.asyncio
async def test_circleci_job_artifacts_stops_at_limit_across_jobs() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [ARTIFACT]})

    adapter = CircleCIJobArtifactsImportAdapter(
        token="circle-token",
        config={"project_slug": "gh/example/tool", "job_numbers": [101, 102]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_circleci_job_artifacts_filters_configured_branches_when_present() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {**ARTIFACT, "path": "main.txt", "branch": "main"},
                    {**ARTIFACT, "path": "dev.txt", "branch": "dev"},
                    {**ARTIFACT, "path": "unknown.txt", "branch": None},
                ]
            },
        )

    adapter = CircleCIJobArtifactsImportAdapter(
        token="circle-token",
        config={"project_slug": "gh/example/tool", "job_number": 101, "branches": ["main"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert [signal.metadata["artifact_path"] for signal in signals] == ["main.txt", "unknown.txt"]


@pytest.mark.asyncio
async def test_circleci_job_artifacts_missing_auth_config_limit_or_api_failure_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CIRCLECI_TOKEN", raising=False)
    monkeypatch.delenv("CIRCLE_TOKEN", raising=False)

    assert await CircleCIJobArtifactsImportAdapter(
        config={"project_slug": "gh/example/tool", "job_number": 101}
    ).fetch() == []
    assert await CircleCIJobArtifactsImportAdapter(token="token", config={"job_number": 101}).fetch() == []
    assert await CircleCIJobArtifactsImportAdapter(
        token="token", config={"project_slug": "gh/example/tool"}
    ).fetch() == []
    assert await CircleCIJobArtifactsImportAdapter(
        token="token", config={"project_slug": "gh/example/tool", "job_number": 101}
    ).fetch(limit=0) == []

    failing = CircleCIJobArtifactsImportAdapter(
        token="bad",
        config={"project_slug": "gh/example/tool", "job_number": 101},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=1) == []
