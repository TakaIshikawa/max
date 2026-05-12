"""Tests for GitHub workflow runs import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_workflow_runs_adapter import GitHubWorkflowRunsImportAdapter


RUN = {
    "id": 123,
    "name": "CI",
    "run_number": 42,
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/example/tool/actions/runs/123",
    "head_branch": "main",
    "head_sha": "abc123",
    "event": "push",
    "created_at": "2026-05-01T10:00:00Z",
    "run_started_at": "2026-05-01T10:01:00Z",
    "updated_at": "2026-05-01T10:06:30Z",
    "actor": {"login": "octocat", "id": 1},
}


@pytest.mark.asyncio
async def test_github_workflow_runs_fetch_filters_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"workflow_runs": [RUN]})
        return httpx.Response(200, json={"workflow_runs": [{**RUN, "id": 124, "run_number": 43}]})

    adapter = GitHubWorkflowRunsImportAdapter(
        token="github_token",
        api_url="https://api.github.test",
        config={
            "repositories": ["example/tool"],
            "branch": "main",
            "event": "push",
            "status": "completed",
            "per_page": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/repos/example/tool/actions/runs"
    assert requests[0].url.params["branch"] == "main"
    assert requests[0].url.params["event"] == "push"
    assert requests[0].url.params["status"] == "completed"
    assert [signal.metadata["run_id"] for signal in signals] == [123, 124]
    assert signals[0].source_adapter == "github_workflow_runs_import"
    assert signals[0].metadata["repository"] == "example/tool"
    assert signals[0].metadata["workflow_name"] == "CI"
    assert signals[0].metadata["conclusion"] == "failure"
    assert signals[0].metadata["branch"] == "main"
    assert signals[0].metadata["event"] == "push"
    assert signals[0].metadata["duration_seconds"] == 330


@pytest.mark.asyncio
async def test_github_workflow_runs_empty_without_token_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubWorkflowRunsImportAdapter(config={"repositories": ["example/tool"]}).fetch() == []
    assert await GitHubWorkflowRunsImportAdapter(token="token").fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = GitHubWorkflowRunsImportAdapter(
        token="bad",
        config={"repositories": ["example/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
