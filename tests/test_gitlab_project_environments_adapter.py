"""Tests for GitLab project environments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_project_environments_adapter import (
    GitLabProjectEnvironmentAdapter,
    GitLabProjectEnvironmentsAdapter,
)
from max.types.signal import SignalSourceType


def _environment(number: int, *, state: str = "available") -> dict:
    return {
        "id": 700 + number,
        "name": f"review/app-{number}",
        "slug": f"review-app-{number}",
        "state": state,
        "tier": "staging",
        "external_url": f"https://review-{number}.example.test",
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "last_deployment": {
            "id": 900 + number,
            "iid": number,
            "status": "success",
            "ref": "main",
            "sha": f"abc{number}",
            "created_at": "2026-05-02T09:00:00Z",
            "finished_at": "2026-05-02T09:05:00Z",
            "deployable": {"id": 300 + number, "name": "deploy", "status": "success"},
        },
    }


@pytest.mark.asyncio
async def test_gitlab_project_environments_paginates_filters_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_environment(1)], headers={"X-Next-Page": "2"})
        if len(requests) == 2:
            return httpx.Response(200, json=[_environment(2, state="stopped")])
        return httpx.Response(200, json=[])

    adapter = GitLabProjectEnvironmentsAdapter(
        private_token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={
            "project_path": "group/app",
            "per_page": 1,
            "search": "review",
            "states": ["available", "stopped"],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert GitLabProjectEnvironmentAdapter is GitLabProjectEnvironmentsAdapter
    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Fapp/environments"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["search"] == "review"
    assert requests[0].url.params["states"] == "available,stopped"
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["environment_id"] for signal in signals] == [701, 702]

    signal = signals[0]
    assert signal.id == "gitlab-project-environment:group/app:701"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "gitlab_project_environments_import"
    assert signal.title == "GitLab environment review/app-1"
    assert signal.url == "https://review-1.example.test"
    assert signal.metadata["project_id"] == "group/app"
    assert signal.metadata["name"] == "review/app-1"
    assert signal.metadata["state"] == "available"
    assert signal.metadata["tier"] == "staging"
    assert signal.metadata["slug"] == "review-app-1"
    assert signal.metadata["external_url"] == "https://review-1.example.test"
    assert signal.metadata["latest_deployment"]["id"] == 901
    assert signal.metadata["latest_deployment"]["deployable"]["name"] == "deploy"
    assert signal.metadata["raw"]["id"] == 701
    assert "project-environment" in signal.tags


@pytest.mark.asyncio
async def test_gitlab_project_environments_uses_env_config_and_api_url_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env-token")
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "platform/app")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.internal")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_environment(1)])

    adapter = GitLabProjectEnvironmentsAdapter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/platform%2Fapp/environments"
    assert requests[0].headers["PRIVATE-TOKEN"] == "env-token"
    assert str(requests[0].url).startswith("https://gitlab.internal/api/v4/")


@pytest.mark.asyncio
async def test_gitlab_project_environments_respects_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_environment(1), _environment(2), _environment(3)])

    adapter = GitLabProjectEnvironmentsAdapter(
        token="token",
        config={"project_id": "42", "per_page": 100},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["environment_id"] for signal in signals] == [701, 702]


@pytest.mark.asyncio
async def test_gitlab_project_environments_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_PATH", raising=False)

    assert await GitLabProjectEnvironmentsAdapter(config={"project_id": "1"}).fetch() == []
    assert await GitLabProjectEnvironmentsAdapter(token="token").fetch() == []
    assert await GitLabProjectEnvironmentsAdapter(token="token", config={"project_id": "1"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_project_environments_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitLabProjectEnvironmentsAdapter(
        token="token",
        config={"project_id": "1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
