"""Tests for GitLab project members import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_project_members_adapter import GitLabProjectMembersAdapter


def _member(number: int, *, state: str = "active", access_level: int = 30) -> dict:
    return {
        "id": 100 + number,
        "username": f"user{number}",
        "name": f"User {number}",
        "state": state,
        "access_level": access_level,
        "created_at": "2026-05-01T10:00:00Z",
        "web_url": f"https://gitlab.example/users/user{number}",
        "avatar_url": f"https://gitlab.example/uploads/user{number}.png",
        "expires_at": None,
    }


@pytest.mark.asyncio
async def test_gitlab_project_members_paginates_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_member(1), _member(2, state="blocked")])
        return httpx.Response(200, json=[_member(3, access_level=40)])

    adapter = GitLabProjectMembersAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4",
        config={"project_ids": ["group/tool"], "states": ["active"], "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab_token"
    assert str(requests[0].url).startswith(
        "https://gitlab.example/api/v4/projects/group%2Ftool/members?"
    )
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["username"] for signal in signals] == ["user1", "user3"]
    assert signals[0].source_adapter == "gitlab_project_members_import"
    assert signals[0].title == "User 1"
    assert signals[0].url == "https://gitlab.example/users/user1"
    assert signals[0].author == "user1"
    assert signals[0].metadata["project_id"] == "group/tool"
    assert signals[0].metadata["name"] == "User 1"
    assert signals[0].metadata["access_level"] == 30
    assert signals[0].metadata["state"] == "active"
    assert signals[0].metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signals[0].metadata["web_url"] == "https://gitlab.example/users/user1"
    assert signals[0].metadata["evidence"] == ["adoption", "stakeholder", "implementation-risk"]
    assert "project-member" in signals[0].tags


@pytest.mark.asyncio
async def test_gitlab_project_members_respects_limit_across_projects() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_member(len(requests))])

    adapter = GitLabProjectMembersAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4",
        config={"project_ids": ["1", "2"], "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert [signal.metadata["project_id"] for signal in signals] == ["1"]


@pytest.mark.asyncio
async def test_gitlab_project_members_uses_inherited_members_endpoint() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_member(1)])

    adapter = GitLabProjectMembersAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4",
        config={"project_ids": ["1"], "include_inherited": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=1)

    assert requests[0].url.path == "/api/v4/projects/1/members/all"


@pytest.mark.asyncio
async def test_gitlab_project_members_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabProjectMembersAdapter(config={"project_ids": ["1"]}).fetch() == []
    assert await GitLabProjectMembersAdapter(token="token").fetch() == []
    assert (
        await GitLabProjectMembersAdapter(token="token", config={"project_ids": ["1"]}).fetch(
            limit=0
        )
        == []
    )


@pytest.mark.asyncio
async def test_gitlab_project_members_http_error_returns_partial_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/1/members"):
            return httpx.Response(200, json=[_member(1)])
        return httpx.Response(500)

    adapter = GitLabProjectMembersAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4",
        config={"project_ids": ["1", "2"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert [signal.metadata["username"] for signal in signals] == ["user1"]
