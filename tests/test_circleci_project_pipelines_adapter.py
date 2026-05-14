"""Tests for CircleCI project pipelines import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.circleci_project_pipelines_adapter import CircleCIProjectPipelinesImportAdapter
from max.types.signal import SignalSourceType


PIPELINE = {
    "id": "pipeline-id-1",
    "number": 42,
    "project_slug": "gh/example/tool",
    "state": "errored",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:01:00Z",
    "web_url": "https://app.circleci.com/pipelines/github/example/tool/42",
    "vcs": {
        "branch": "main",
        "revision": "abcdef1234567890",
        "origin_repository_url": "https://github.com/example/tool",
    },
    "trigger": {"type": "webhook", "actor": {"login": "octocat"}, "received_at": "2026-05-01T10:00:00Z"},
    "errors": [{"message": "config failed"}],
}


@pytest.mark.asyncio
async def test_circleci_project_pipelines_fetches_pages_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "page-token" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "items": [PIPELINE, {**PIPELINE, "id": "ignored", "state": "created"}],
                    "next_page_token": "next",
                },
            )
        return httpx.Response(200, json={"items": [{**PIPELINE, "id": "pipeline-id-2", "number": 43}]})

    adapter = CircleCIProjectPipelinesImportAdapter(
        token="circle-token",
        api_url="https://circleci.test/api/v2",
        config={
            "project_slug": "gh/example/tool",
            "branch": "main",
            "mine": True,
            "statuses": ["errored"],
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Circle-Token"] == "circle-token"
    assert requests[0].url.path == "/api/v2/project/gh/example/tool/pipeline"
    assert requests[0].url.params["page-size"] == "1"
    assert requests[0].url.params["branch"] == "main"
    assert requests[0].url.params["mine"] == "true"
    assert requests[1].url.params["page-token"] == "next"
    assert [signal.metadata["pipeline_id"] for signal in signals] == ["pipeline-id-1", "pipeline-id-2"]

    signal = signals[0]
    assert signal.id == "circleci-project-pipeline:gh/example/tool:pipeline-id-1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "circleci_project_pipelines_import"
    assert signal.title == "gh/example/tool pipeline #42 errored"
    assert signal.content == "state errored, branch main, revision abcdef123456"
    assert signal.url == PIPELINE["web_url"]
    assert signal.author == "octocat"
    assert signal.published_at is not None
    assert signal.metadata["project_slug"] == "gh/example/tool"
    assert signal.metadata["state"] == "errored"
    assert signal.metadata["revision"] == "abcdef1234567890"
    assert signal.metadata["branch"] == "main"
    assert signal.metadata["vcs"] == PIPELINE["vcs"]
    assert signal.metadata["raw"] == PIPELINE
    assert "pipeline" in signal.tags


@pytest.mark.asyncio
async def test_circleci_project_pipelines_multiple_projects_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [{**PIPELINE, "project_slug": None}]})

    adapter = CircleCIProjectPipelinesImportAdapter(
        token="circle-token",
        config={"project_slugs": ["gh/example/tool", "gh/example/api"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert signals[0].metadata["project_slug"] == "gh/example/tool"


@pytest.mark.asyncio
async def test_circleci_project_pipelines_supports_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRCLE_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [PIPELINE]})

    adapter = CircleCIProjectPipelinesImportAdapter(
        config={"project_slug": "gh/example/tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Circle-Token"] == "env-token"
    assert signals[0].metadata["pipeline_id"] == "pipeline-id-1"


@pytest.mark.asyncio
async def test_circleci_project_pipelines_missing_config_auth_or_failure_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CIRCLECI_TOKEN", raising=False)
    monkeypatch.delenv("CIRCLE_TOKEN", raising=False)

    assert await CircleCIProjectPipelinesImportAdapter(config={"project_slug": "gh/example/tool"}).fetch() == []
    assert await CircleCIProjectPipelinesImportAdapter(token="token").fetch() == []
    assert await CircleCIProjectPipelinesImportAdapter(token="token", config={"project_slug": "gh/example/tool"}).fetch(limit=0) == []

    failing = CircleCIProjectPipelinesImportAdapter(
        token="bad",
        config={"project_slug": "gh/example/tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )

    assert await failing.fetch() == []
