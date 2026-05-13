"""Tests for Azure DevOps git commits import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.azure_devops_git_commits_adapter import AzureDevOpsGitCommitsAdapter
from max.types.signal import SignalSourceType


COMMIT = {
    "commitId": "abcdef1234567890abcdef1234567890abcdef12",
    "author": {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "date": "2026-05-01T10:00:00Z",
        "imageUrl": "https://dev.azure.test/avatar/ada",
    },
    "committer": {
        "name": "Grace Hopper",
        "email": "grace@example.com",
        "date": "2026-05-01T10:05:00Z",
    },
    "comment": "Add Git import\n\nImplements pagination.",
    "changeCounts": {"Add": 3, "Edit": 2, "Delete": 1},
    "url": "https://dev.azure.test/acme/max/_apis/git/repositories/repo-1/commits/abcdef",
    "remoteUrl": "https://dev.azure.com/acme/max/_git/repo-1/commit/abcdef1234567890abcdef1234567890abcdef12",
    "parents": ["parent-sha"],
}


@pytest.mark.asyncio
async def test_azure_devops_git_commits_fetches_paginates_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"value": [{**COMMIT, "commitId": "sha-1"}]},
                headers={"x-ms-continuationtoken": "next-token"},
            )
        return httpx.Response(200, json={"value": [{**COMMIT, "commitId": "sha-2"}]})

    adapter = AzureDevOpsGitCommitsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        api_url="https://dev.azure.test",
        config={
            "api_version": "7.0",
            "branch": "refs/heads/main",
            "from_date": "2026-05-01T00:00:00Z",
            "to_date": "2026-05-02T00:00:00Z",
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["searchCriteria.$top"] for request in requests] == ["1", "1"]
    assert requests[0].url.path == "/acme/max/_apis/git/repositories/repo-1/commits"
    assert requests[0].url.params["api-version"] == "7.0"
    assert requests[0].url.params["searchCriteria.itemVersion.version"] == "main"
    assert requests[0].url.params["searchCriteria.itemVersion.versionType"] == "branch"
    assert requests[0].url.params["searchCriteria.fromDate"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["searchCriteria.toDate"] == "2026-05-02T00:00:00Z"
    assert "continuationToken" not in requests[0].url.params
    assert requests[1].url.params["continuationToken"] == "next-token"
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b":pat").decode()
    assert requests[0].headers["User-Agent"] == "max-azure-devops-git-commits-import/1"

    assert len(signals) == 2
    signal = signals[0]
    assert signal.id == "azure-devops-commit:acme/max/repo-1:sha-1"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "azure_devops_git_commits_import"
    assert signal.title == "max commit sha-1: Add Git import"
    assert signal.content == COMMIT["comment"]
    assert signal.url == COMMIT["remoteUrl"]
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["organization"] == "acme"
    assert signal.metadata["project"] == "max"
    assert signal.metadata["repository_id"] == "repo-1"
    assert signal.metadata["commit_id"] == "sha-1"
    assert signal.metadata["comment"] == COMMIT["comment"]
    assert signal.metadata["author"]["email"] == "ada@example.com"
    assert signal.metadata["committer"]["name"] == "Grace Hopper"
    assert signal.metadata["author_date"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["committer_date"] == "2026-05-01T10:05:00Z"
    assert signal.metadata["change_counts"] == {"add": 3, "edit": 2, "delete": 1}
    assert signal.metadata["branch"] == "refs/heads/main"
    assert signal.metadata["from_date"] == "2026-05-01T00:00:00Z"
    assert signal.metadata["to_date"] == "2026-05-02T00:00:00Z"
    assert signal.metadata["remote_url"] == COMMIT["remoteUrl"]
    assert signal.metadata["parents"] == ["parent-sha"]
    assert signal.metadata["raw"]["commitId"] == "sha-1"
    assert {"azure-devops", "commit", "refs/heads/main"}.issubset(set(signal.tags))


@pytest.mark.asyncio
async def test_azure_devops_git_commits_uses_bearer_token_and_config_aliases() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[COMMIT])

    adapter = AzureDevOpsGitCommitsAdapter(
        config={
            "organization": "acme",
            "project": "max",
            "repository": "repo-alias",
            "bearer_token": "bearer-token",
            "api_url": "https://dev.azure.test/",
            "per_page": 25,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].headers["Authorization"] == "Bearer bearer-token"
    assert requests[0].url.path == "/acme/max/_apis/git/repositories/repo-alias/commits"
    assert requests[0].url.params["searchCriteria.$top"] == "5"
    assert signals[0].metadata["repository_id"] == "repo-alias"


@pytest.mark.asyncio
async def test_azure_devops_git_commits_respects_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "value": [
                    {**COMMIT, "commitId": "sha-1"},
                    {**COMMIT, "commitId": "sha-2"},
                ]
            },
            headers={"x-ms-continuationtoken": "ignored"},
        )

    adapter = AzureDevOpsGitCommitsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["searchCriteria.$top"] == "1"
    assert [signal.metadata["commit_id"] for signal in signals] == ["sha-1"]


@pytest.mark.asyncio
async def test_azure_devops_git_commits_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DEVOPS_ORGANIZATION", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_REPOSITORY_ID", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_REPOSITORY", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_TOKEN", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_BEARER_TOKEN", raising=False)

    assert await AzureDevOpsGitCommitsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
    ).fetch() == []
    assert await AzureDevOpsGitCommitsAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
    ).fetch() == []
    assert await AzureDevOpsGitCommitsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
    ).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_azure_devops_git_commits_http_failure_or_malformed_response_returns_empty() -> None:
    failing = AzureDevOpsGitCommitsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []

    malformed = AzureDevOpsGitCommitsAdapter(
        organization="acme",
        project="max",
        repository_id="repo-1",
        personal_access_token="pat",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"bad": "shape"}))),
    )
    assert await malformed.fetch(limit=1) == []
