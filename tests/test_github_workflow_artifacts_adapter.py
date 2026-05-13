"""Tests for GitHub workflow artifacts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_workflow_artifacts_adapter import (
    GitHubWorkflowArtifactsAdapter,
    GitHubWorkflowArtifactsImportAdapter,
)


def _artifact(number: int, *, name: str | None = None, expired: bool = False) -> dict:
    return {
        "id": 1000 + number,
        "node_id": f"MDg6QXJ0aWZhY3Q{number}",
        "name": name or f"build-{number}",
        "size_in_bytes": 2048 + number,
        "url": f"https://api.github.test/repos/acme/tool/actions/artifacts/{1000 + number}",
        "archive_download_url": f"https://api.github.test/repos/acme/tool/actions/artifacts/{1000 + number}/zip",
        "expired": expired,
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-01T10:05:00Z",
        "expires_at": "2026-08-01T10:00:00Z",
        "workflow_run": {
            "id": 5000 + number,
            "repository_id": 10,
            "head_repository_id": 10,
            "head_branch": "main",
            "head_sha": f"abc{number}",
        },
    }


@pytest.mark.asyncio
async def test_github_workflow_artifacts_paginates_across_repositories_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/repos/acme/tool/actions/artifacts" and request.url.params["page"] == "1":
            return httpx.Response(200, json={"total_count": 3, "artifacts": [_artifact(1), _artifact(2)]})
        if request.url.path == "/repos/acme/tool/actions/artifacts" and request.url.params["page"] == "2":
            return httpx.Response(200, json={"total_count": 3, "artifacts": [_artifact(3, expired=True)]})
        return httpx.Response(200, json={"total_count": 1, "artifacts": [_artifact(4)]})

    adapter = GitHubWorkflowArtifactsImportAdapter(
        token="gh-token",
        api_url="https://api.github.test",
        config={"repositories": ["acme/tool", "acme/other"], "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=4)

    assert GitHubWorkflowArtifactsAdapter is GitHubWorkflowArtifactsImportAdapter
    assert len(requests) == 3
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    assert requests[0].headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[2].url.path == "/repos/acme/other/actions/artifacts"
    assert len(signals) == 4
    signal = signals[0]
    assert signal.id == "github-workflow-artifact:acme/tool:1001"
    assert signal.source_adapter == "github_workflow_artifacts_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "acme/tool workflow artifact build-1"
    assert signal.url == "https://api.github.test/repos/acme/tool/actions/artifacts/1001/zip"
    assert signal.published_at is not None
    assert signal.metadata["artifact_id"] == 1001
    assert signal.metadata["repository"] == "acme/tool"
    assert signal.metadata["name"] == "build-1"
    assert signal.metadata["size"] == 2049
    assert signal.metadata["size_in_bytes"] == 2049
    assert signal.metadata["expired"] is False
    assert signal.metadata["archive_download_url"].endswith("/1001/zip")
    assert signal.metadata["workflow_run"]["id"] == 5001
    assert signal.metadata["workflow_run"]["head_branch"] == "main"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-01T10:05:00Z"
    assert signal.metadata["expires_at"] == "2026-08-01T10:00:00Z"
    assert "workflow-artifact" in signal.tags
    assert "active" in signal.tags
    assert "expired" in signals[2].tags


@pytest.mark.asyncio
async def test_github_workflow_artifacts_skips_invalid_repositories_and_accepts_repos_alias() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"total_count": 1, "artifacts": [_artifact(1)]})

    adapter = GitHubWorkflowArtifactsImportAdapter(
        token="gh-token",
        config={"repos": ["missing-slash", "acme/tool", "too/many/slashes", "/empty-owner"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].url.path == "/repos/acme/tool/actions/artifacts"
    assert signals[0].metadata["repository"] == "acme/tool"


@pytest.mark.asyncio
async def test_github_workflow_artifacts_filters_name_and_expired() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "total_count": 3,
                "artifacts": [
                    _artifact(1, name="dist", expired=False),
                    _artifact(2, name="logs", expired=False),
                    _artifact(3, name="dist", expired=True),
                ],
            },
        )

    adapter = GitHubWorkflowArtifactsImportAdapter(
        token="gh-token",
        config={"repositories": "acme/tool", "name": "dist", "expired": "true"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["name"] == "dist"
    assert [signal.metadata["artifact_id"] for signal in signals] == [1003]
    assert signals[0].metadata["name"] == "dist"
    assert signals[0].metadata["expired"] is True


@pytest.mark.asyncio
async def test_github_workflow_artifacts_empty_without_required_config_auth_or_positive_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert await GitHubWorkflowArtifactsImportAdapter(config={"repositories": ["acme/tool"]}).fetch() == []
    assert await GitHubWorkflowArtifactsImportAdapter(token="token").fetch() == []
    assert await GitHubWorkflowArtifactsImportAdapter(token="token", config={"repositories": ["acme/tool"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_github_workflow_artifacts_reads_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"total_count": 1, "artifacts": [_artifact(1)]})

    adapter = GitHubWorkflowArtifactsImportAdapter(
        config={"repositories": ["acme/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["repository"] == "acme/tool"


@pytest.mark.asyncio
async def test_github_workflow_artifacts_api_or_non_json_failure_returns_empty() -> None:
    failing = GitHubWorkflowArtifactsImportAdapter(
        token="gh-token",
        config={"repositories": ["acme/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = GitHubWorkflowArtifactsImportAdapter(
        token="gh-token",
        config={"repositories": ["acme/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not json"))),
    )
    assert await non_json.fetch(limit=2) == []
