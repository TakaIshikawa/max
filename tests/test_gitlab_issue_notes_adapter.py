"""Tests for GitLab issue notes import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_issue_notes_adapter import GitLabIssueNotesAdapter
from max.types.signal import SignalSourceType


def _note(number: int, *, system: bool = False) -> dict:
    return {
        "id": number,
        "body": f"Customer context {number}",
        "system": system,
        "author": {
            "id": 10 + number,
            "username": f"user{number}",
            "name": f"User {number}",
            "web_url": f"https://gitlab.example/users/user{number}",
        },
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-01T11:00:00Z",
        "noteable_id": 200,
        "noteable_iid": 7,
        "url": f"https://gitlab.example/group/tool/-/issues/7#note_{number}",
    }


@pytest.mark.asyncio
async def test_gitlab_issue_notes_fetches_paginates_and_maps_notes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[_note(1), _note(2, system=True)])
        return httpx.Response(200, json=[_note(3)])

    adapter = GitLabIssueNotesAdapter(
        private_token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={"project_ids": ["group/tool"], "issue_iids": ["7"], "page_size": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert str(requests[0].url).startswith(
        "https://gitlab.example/api/v4/projects/group%2Ftool/issues/7/notes?"
    )
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert [signal.metadata["gitlab_note_id"] for signal in signals] == [1, 3]
    signal = signals[0]
    assert signal.id == "gitlab-issue-note:group/tool:7:1"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "gitlab_issue_notes_import"
    assert signal.title == "GitLab issue 7 note"
    assert signal.content == "Customer context 1"
    assert signal.url == "https://gitlab.example/group/tool/-/issues/7#note_1"
    assert signal.author == "user1"
    assert signal.metadata["project_id"] == "group/tool"
    assert signal.metadata["issue_iid"] == "7"
    assert signal.metadata["system"] is False
    assert signal.metadata["author"]["username"] == "user1"
    assert signal.metadata["raw"]["id"] == 1
    assert "issue-note" in signal.tags


@pytest.mark.asyncio
async def test_gitlab_issue_notes_can_include_system_notes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_note(1, system=True)])

    adapter = GitLabIssueNotesAdapter(
        token="gitlab-token",
        gitlab_url="https://gitlab.example",
        config={"project_ids": ["1"], "issue_iids": ["2"], "system_notes": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/api/v4/projects/1/issues/2/notes"
    assert len(signals) == 1
    assert signals[0].metadata["system"] is True
    assert "system-note" in signals[0].tags


@pytest.mark.asyncio
async def test_gitlab_issue_notes_respects_limits_across_projects_and_issues() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_note(len(requests))])

    adapter = GitLabIssueNotesAdapter(
        private_token="gitlab-token",
        config={"project_ids": ["1", "2"], "issue_iids": ["10", "11"], "per_issue_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert [signal.metadata["issue_iid"] for signal in signals] == ["10", "11"]


@pytest.mark.asyncio
async def test_gitlab_issue_notes_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabIssueNotesAdapter(config={"project_ids": ["1"], "issue_iids": ["2"]}).fetch() == []
    assert await GitLabIssueNotesAdapter(private_token="token", config={"issue_iids": ["2"]}).fetch() == []
    assert await GitLabIssueNotesAdapter(private_token="token", config={"project_ids": ["1"]}).fetch() == []
    assert (
        await GitLabIssueNotesAdapter(
            private_token="token",
            config={"project_ids": ["1"], "issue_iids": ["2"]},
        ).fetch(limit=0)
        == []
    )


@pytest.mark.asyncio
async def test_gitlab_issue_notes_failure_returns_partial_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/issues/1/notes"):
            return httpx.Response(200, json=[_note(1)])
        return httpx.Response(500)

    adapter = GitLabIssueNotesAdapter(
        private_token="gitlab-token",
        config={"project_ids": ["1"], "issue_iids": ["1", "2"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert [signal.metadata["gitlab_note_id"] for signal in signals] == [1]
