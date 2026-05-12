"""Tests for Azure DevOps pull request threads import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.azure_devops_pull_request_threads_adapter import AzureDevOpsPullRequestThreadsAdapter


THREAD = {
    "id": 10,
    "status": "active",
    "threadContext": {
        "filePath": "/src/app.py",
        "rightFileStart": {"line": 12, "offset": 1},
        "rightFileEnd": {"line": 13, "offset": 5},
    },
    "pullRequestThreadContext": {"changeTrackingId": 1, "iterationContext": {"firstComparingIteration": 1, "secondComparingIteration": 2}},
    "properties": {"CodeReviewThreadType": {"$type": "System.String", "$value": "text"}},
    "comments": [
        {
            "id": 100,
            "content": "Please handle the empty response case.",
            "commentType": "text",
            "author": {"displayName": "Ada", "uniqueName": "ada@example.com", "id": "a"},
            "publishedDate": "2026-05-01T10:00:00Z",
            "lastUpdatedDate": "2026-05-01T11:00:00Z",
        }
    ],
}


@pytest.mark.asyncio
async def test_azure_devops_pull_request_threads_fetches_and_maps_comments() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"value": [THREAD]})

    adapter = AzureDevOpsPullRequestThreadsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        config={"pull_request_ids": [42], "api_version": "7.0"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert len(requests) == 1
    assert requests[0].url.path == "/acme/max/_apis/git/repositories/repo-1/pullRequests/42/threads"
    assert requests[0].url.params["api-version"] == "7.0"
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "azure-devops-pr-thread-comment:acme/max/repo-1:42:10:100"
    assert signal.source_adapter == "azure_devops_pull_request_threads_import"
    assert signal.title == "max PR 42 thread 10 comment"
    assert signal.content == "Please handle the empty response case."
    assert signal.author == "Ada"
    assert signal.url == "https://dev.azure.com/acme/max/_git/repo-1/pullrequest/42?_a=files&discussionId=10"
    assert signal.metadata["organization"] == "acme"
    assert signal.metadata["project"] == "max"
    assert signal.metadata["repository_id"] == "repo-1"
    assert signal.metadata["pull_request_id"] == 42
    assert signal.metadata["thread_id"] == 10
    assert signal.metadata["comment_id"] == 100
    assert signal.metadata["status"] == "active"
    assert signal.metadata["is_resolved"] is False
    assert signal.metadata["author"]["uniqueName"] == "ada@example.com"
    assert signal.metadata["published_date"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["last_updated_date"] == "2026-05-01T11:00:00Z"
    assert signal.metadata["file_path"] == "/src/app.py"
    assert signal.metadata["right_file_start"] == {"line": 12, "offset": 1}
    assert "pull-request-thread" in signal.tags


@pytest.mark.asyncio
async def test_azure_devops_pull_request_threads_excludes_resolved_by_default_and_can_include() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [{**THREAD, "id": 11, "status": "closed"}]})

    closed_adapter = AzureDevOpsPullRequestThreadsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        config={"pull_request_ids": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await closed_adapter.fetch(limit=10) == []

    include_adapter = AzureDevOpsPullRequestThreadsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        config={"pull_request_ids": [42], "include_resolved": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await include_adapter.fetch(limit=10)
    assert len(signals) == 1
    assert signals[0].metadata["status"] == "closed"
    assert signals[0].metadata["is_resolved"] is True


@pytest.mark.asyncio
async def test_azure_devops_pull_request_threads_respects_limit_across_pull_requests() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        pr_id = request.url.path.split("/pullRequests/", 1)[1].split("/", 1)[0]
        return httpx.Response(
            200,
            json={
                "value": [
                    {**THREAD, "id": int(f"{pr_id}1"), "comments": [{**THREAD["comments"][0], "id": int(f"{pr_id}01")}]},
                    {**THREAD, "id": int(f"{pr_id}2"), "comments": [{**THREAD["comments"][0], "id": int(f"{pr_id}02")}]},
                ]
            },
        )

    adapter = AzureDevOpsPullRequestThreadsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        config={"pull_request_ids": [42, 43], "per_pr_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["pull_request_id"] for signal in signals] == [42, 43]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_azure_devops_pull_request_threads_missing_config_or_failure_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DEVOPS_ORGANIZATION", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_TOKEN", raising=False)

    assert await AzureDevOpsPullRequestThreadsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        config={"pull_request_ids": [42]},
    ).fetch() == []
    assert await AzureDevOpsPullRequestThreadsAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"pull_request_ids": [42]},
    ).fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = AzureDevOpsPullRequestThreadsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        config={"pull_request_ids": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
