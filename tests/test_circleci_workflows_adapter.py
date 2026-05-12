"""Tests for CircleCI workflows import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.circleci_workflows_adapter import CircleCIWorkflowsImportAdapter


PIPELINE = {
    "id": "pipeline-1",
    "number": 42,
    "project_slug": "gh/example/tool",
    "created_at": "2026-05-01T09:59:00Z",
    "vcs": {
        "branch": "main",
        "revision": "abc123",
        "commit": {"subject": "Ship the workflow adapter"},
    },
    "web_url": "https://app.circleci.com/pipelines/github/example/tool/42",
}

WORKFLOW = {
    "id": "workflow-1",
    "pipeline_id": "pipeline-1",
    "name": "build-and-test",
    "project_slug": "gh/example/tool",
    "status": "failed",
    "pipeline_number": 42,
    "created_at": "2026-05-01T10:00:00Z",
    "stopped_at": "2026-05-01T10:05:30Z",
    "started_by": "user-1",
    "url": "https://app.circleci.com/pipelines/github/example/tool/42/workflows/workflow-1",
}


@pytest.mark.asyncio
async def test_circleci_workflows_fetches_pipelines_and_maps_workflows() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/project/gh/example/tool/pipeline":
            return httpx.Response(200, json={"items": [PIPELINE]})
        if request.url.path == "/api/v2/pipeline/pipeline-1/workflow":
            return httpx.Response(200, json={"items": [WORKFLOW]})
        return httpx.Response(404)

    adapter = CircleCIWorkflowsImportAdapter(
        token="circle-token",
        api_url="https://circleci.test/api/v2",
        config={"project_slugs": ["gh/example/tool"], "branch": "main"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].headers["Circle-Token"] == "circle-token"
    assert requests[0].url.params["branch"] == "main"
    assert requests[1].url.path == "/api/v2/pipeline/pipeline-1/workflow"
    assert len(signals) == 1
    assert signals[0].source_adapter == "circleci_workflows_import"
    assert signals[0].title == "gh/example/tool build-and-test #42 failed"
    assert signals[0].content == "Ship the workflow adapter"
    assert signals[0].url == WORKFLOW["url"]
    assert signals[0].author == "user-1"
    assert signals[0].metadata["workflow_id"] == "workflow-1"
    assert signals[0].metadata["status"] == "failed"
    assert signals[0].metadata["duration_seconds"] == 330
    assert signals[0].metadata["pipeline_number"] == 42
    assert signals[0].metadata["branch"] == "main"
    assert signals[0].metadata["commit"] == "abc123"


@pytest.mark.asyncio
async def test_circleci_workflows_respects_limit_across_projects_and_pages() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/project/gh/example/one/pipeline":
            if "page-token" not in request.url.params:
                return httpx.Response(200, json={"items": [{**PIPELINE, "id": "pipeline-1"}], "next_page_token": "next"})
            return httpx.Response(200, json={"items": [{**PIPELINE, "id": "pipeline-2", "number": 43}]})
        if request.url.path == "/api/v2/project/gh/example/two/pipeline":
            return httpx.Response(200, json={"items": [{**PIPELINE, "id": "pipeline-3", "number": 44}]})
        if request.url.path == "/api/v2/pipeline/pipeline-1/workflow":
            return httpx.Response(200, json={"items": [{**WORKFLOW, "id": "workflow-1"}]})
        if request.url.path == "/api/v2/pipeline/pipeline-2/workflow":
            return httpx.Response(200, json={"items": [{**WORKFLOW, "id": "workflow-2", "pipeline_id": "pipeline-2"}]})
        if request.url.path == "/api/v2/pipeline/pipeline-3/workflow":
            return httpx.Response(200, json={"items": [{**WORKFLOW, "id": "workflow-3", "pipeline_id": "pipeline-3"}]})
        return httpx.Response(404)

    adapter = CircleCIWorkflowsImportAdapter(
        token="circle-token",
        api_url="https://circleci.test/api/v2",
        config={"project_slugs": ["gh/example/one", "gh/example/two"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["workflow_id"] for signal in signals] == ["workflow-1", "workflow-2"]
    assert [request.url.path for request in requests].count("/api/v2/project/gh/example/two/pipeline") == 0
    assert requests[2].url.params["page-token"] == "next"


@pytest.mark.asyncio
async def test_circleci_workflows_missing_auth_or_config_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CIRCLECI_TOKEN", raising=False)
    monkeypatch.delenv("CIRCLE_TOKEN", raising=False)

    assert await CircleCIWorkflowsImportAdapter(config={"project_slugs": ["gh/example/tool"]}).fetch() == []
    assert await CircleCIWorkflowsImportAdapter(token="token").fetch() == []


@pytest.mark.asyncio
async def test_circleci_workflows_api_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = CircleCIWorkflowsImportAdapter(
        token="bad",
        config={"project_slugs": ["gh/example/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch() == []
