"""Tests for CircleCI jobs import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.circleci_jobs_adapter import CircleCIJobsImportAdapter
from max.types.signal import SignalSourceType


JOB = {
    "id": "job-id-1",
    "job_number": 101,
    "name": "build",
    "project_slug": "gh/example/tool",
    "status": "failed",
    "type": "build",
    "started_at": "2026-05-01T10:00:00Z",
    "stopped_at": "2026-05-01T10:02:30Z",
    "started_by": "user-1",
    "web_url": "https://app.circleci.com/pipelines/github/example/tool/42/workflows/workflow-1/jobs/101",
    "dependencies": ["checkout"],
    "parallel_runs": [{"index": 0, "status": "failed"}],
}


@pytest.mark.asyncio
async def test_circleci_jobs_fetches_workflow_jobs_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [JOB]})

    adapter = CircleCIJobsImportAdapter(
        token="circle-token",
        api_url="https://circleci.test/api/v2",
        config={"workflow_ids": ["workflow-1"], "page_size": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].url.path == "/api/v2/workflow/workflow-1/job"
    assert requests[0].url.params["page-size"] == "25"
    assert requests[0].headers["Circle-Token"] == "circle-token"
    assert len(signals) == 1
    assert signals[0].id == "circleci-job:workflow-1:job-id-1"
    assert signals[0].source_type == SignalSourceType.FAILURE_DATA
    assert signals[0].source_adapter == "circleci_jobs_import"
    assert signals[0].title == "gh/example/tool build #101 failed"
    assert signals[0].url == JOB["web_url"]
    assert signals[0].author == "user-1"
    assert signals[0].metadata["workflow_id"] == "workflow-1"
    assert signals[0].metadata["job_id"] == "job-id-1"
    assert signals[0].metadata["status"] == "failed"
    assert signals[0].metadata["duration_seconds"] == 150
    assert signals[0].metadata["raw"] == JOB
    assert "job" in signals[0].tags


@pytest.mark.asyncio
async def test_circleci_jobs_follows_next_page_token_and_honors_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "page-token" not in request.url.params:
            return httpx.Response(200, json={"items": [{**JOB, "id": "job-1"}], "next_page_token": "next"})
        return httpx.Response(200, json={"items": [{**JOB, "id": "job-2", "job_number": 102}]})

    adapter = CircleCIJobsImportAdapter(
        token="circle-token",
        config={"workflow_ids": ["workflow-1"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["job_id"] for signal in signals] == ["job-1", "job-2"]
    assert requests[1].url.params["page-token"] == "next"


@pytest.mark.asyncio
async def test_circleci_jobs_filters_statuses_and_continues_pagination() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "page-token" not in request.url.params:
            return httpx.Response(200, json={"items": [{**JOB, "id": "job-1", "status": "success"}], "next_page_token": "next"})
        return httpx.Response(200, json={"items": [{**JOB, "id": "job-2", "status": "failed"}]})

    adapter = CircleCIJobsImportAdapter(
        token="circle-token",
        config={"workflow_ids": ["workflow-1"], "statuses": ["failed"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert [signal.metadata["job_id"] for signal in signals] == ["job-2"]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_circleci_jobs_accepts_project_slug_without_requiring_it() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [{k: v for k, v in JOB.items() if k != "project_slug"}]})

    adapter = CircleCIJobsImportAdapter(
        token="circle-token",
        config={"workflow_ids": ["workflow-1"], "project_slug": "gh/example/tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].metadata["project_slug"] == "gh/example/tool"
    assert signals[0].title == "gh/example/tool build #101 failed"


@pytest.mark.asyncio
async def test_circleci_jobs_missing_auth_or_config_and_api_failure_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CIRCLECI_TOKEN", raising=False)
    monkeypatch.delenv("CIRCLE_TOKEN", raising=False)

    assert await CircleCIJobsImportAdapter(config={"workflow_ids": ["workflow-1"]}).fetch() == []
    assert await CircleCIJobsImportAdapter(token="token").fetch() == []
    assert await CircleCIJobsImportAdapter(token="token", config={"workflow_ids": ["workflow-1"]}).fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = CircleCIJobsImportAdapter(
        token="bad",
        config={"workflow_ids": ["workflow-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch() == []
