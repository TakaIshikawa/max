"""Tests for Jira project versions import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.jira_project_versions_adapter import JiraProjectVersionsAdapter


def _version(number: int, *, released: bool = False, archived: bool = False) -> dict:
    return {
        "id": str(1000 + number),
        "name": f"Release {number}",
        "description": f"Roadmap release {number}",
        "self": f"https://jira.example/rest/api/3/version/{1000 + number}",
        "startDate": "2026-05-01",
        "releaseDate": "2026-05-15",
        "userStartDate": "1/May/26",
        "userReleaseDate": "15/May/26",
        "released": released,
        "archived": archived,
    }


@pytest.mark.asyncio
async def test_jira_project_versions_fetches_projects_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("startAt") == "0":
            return httpx.Response(
                200,
                json={
                    "startAt": 0,
                    "maxResults": 1,
                    "total": 2,
                    "isLast": False,
                    "values": [_version(1)],
                },
            )
        return httpx.Response(
            200,
            json={
                "startAt": 1,
                "maxResults": 1,
                "total": 2,
                "isLast": True,
                "values": [_version(2, released=True)],
            },
        )

    adapter = JiraProjectVersionsAdapter(
        base_url="https://jira.example",
        email="ada@example.com",
        api_token="jira_token",
        config={"project_keys": ["MAX"], "max_results": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/rest/api/3/project/MAX/version"
    assert requests[0].url.params["startAt"] == "0"
    assert requests[0].url.params["maxResults"] == "1"
    assert requests[1].url.params["startAt"] == "1"
    assert requests[0].headers["Accept"] == "application/json"
    assert [signal.metadata["name"] for signal in signals] == ["Release 1", "Release 2"]
    assert signals[0].source_adapter == "jira_project_versions_import"
    assert signals[0].title == "Release 1"
    assert signals[0].content == "Roadmap release 1"
    assert signals[0].url == "https://jira.example/rest/api/3/version/1001"
    assert signals[0].metadata["project_key"] == "MAX"
    assert signals[0].metadata["description"] == "Roadmap release 1"
    assert signals[0].metadata["status"] == "unreleased"
    assert signals[0].metadata["start_date"] == "2026-05-01"
    assert signals[0].metadata["release_date"] == "2026-05-15"
    assert signals[0].metadata["archived"] is False
    assert signals[0].metadata["released"] is False
    assert signals[0].metadata["self"] == "https://jira.example/rest/api/3/version/1001"
    assert signals[1].metadata["status"] == "released"


@pytest.mark.asyncio
async def test_jira_project_versions_bearer_auth_status_filter_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_version(1, released=True), _version(2)])

    adapter = JiraProjectVersionsAdapter(
        base_url="https://jira.example",
        bearer_token="bearer",
        config={"project_keys": ["MAX", "OPS"], "statuses": ["released"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer bearer"
    assert [signal.metadata["status"] for signal in signals] == ["released"]


@pytest.mark.asyncio
async def test_jira_project_versions_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_USERNAME", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_BEARER_TOKEN", raising=False)

    assert await JiraProjectVersionsAdapter(config={"project_keys": ["MAX"]}).fetch() == []
    assert (
        await JiraProjectVersionsAdapter(base_url="https://jira.example", api_token="token").fetch()
        == []
    )
    assert (
        await JiraProjectVersionsAdapter(
            base_url="https://jira.example",
            bearer_token="bearer",
            config={"project_keys": ["MAX"]},
        ).fetch(limit=0)
        == []
    )


@pytest.mark.asyncio
async def test_jira_project_versions_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = JiraProjectVersionsAdapter(
        base_url="https://jira.example",
        bearer_token="bearer",
        config={"project_keys": ["MAX"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch() == []
